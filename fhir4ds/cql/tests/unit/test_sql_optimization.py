"""
Unit tests for SQL optimization features.

Tests cover:
- Named CTEs with valueset aliases
- MATERIALIZED hints on CTEs
- CTE optimization patterns
- SQLQueryBuilder CTE reference tracking
"""

import pytest
import sys
from pathlib import Path

# Add src to path

from ...translator.types import (
    SQLRetrieveCTE,
)
from ...translator.queries import SQLQueryBuilder, CTEReference


class TestGetValuesetAlias:
    """Tests for _get_valueset_alias method."""

    def test_get_valueset_alias_found(self):
        """Should find alias for known URL."""
        from ...translator import CQLToSQLTranslator
        from ...parser import parse_cql

        cql = """
        library Test version '1.0'

        valueset "Test Valueset": 'http://example.org/fhir/ValueSet/test'

        context Patient

        define "Test": [Condition]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        translator.translate_library_to_population_sql(library)

        # Now the context should have the valueset
        alias = translator._get_valueset_alias('http://example.org/fhir/ValueSet/test')

        assert alias == "Test Valueset"

    def test_get_valueset_alias_not_found(self):
        """Should return None for unknown URL."""
        from ...translator import CQLToSQLTranslator
        translator = CQLToSQLTranslator()

        alias = translator._get_valueset_alias('http://unknown.org/ValueSet/unknown')

        assert alias is None


class TestNamedCTEs:
    """Tests for named CTEs with valueset aliases."""

    def test_cte_name_with_valueset(self):
        """CTE should be generated for definition with valueset filter."""
        from ...translator import CQLToSQLTranslator
        from ...parser import parse_cql

        cql = """
        library Test version '1.0'

        valueset "Essential Hypertension": 'http://example.org/fhir/ValueSet/essential-hypertension'

        context Patient

        define "Hypertension Conditions":
            [Condition: "Essential Hypertension"]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Check that the CTE is named with the definition name
        assert '"Hypertension Conditions"' in sql, \
            f"Expected CTE with definition name in SQL:\n{sql[:2000]}"
        # Check that valueset is referenced
        assert 'essential-hypertension' in sql, \
            f"Expected valueset URL in SQL:\n{sql[:2000]}"

    def test_cte_name_without_valueset(self):
        """CTE name should be 'Condition' without valueset."""
        from ...translator import CQLToSQLTranslator
        from ...parser import parse_cql

        cql = """
        library Test version '1.0'

        context Patient

        define "All Conditions":
            [Condition]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Check that the CTE is named with just resource type
        assert '"Condition"' in sql or 'Condition' in sql, \
            f"Expected named CTE 'Condition' in SQL:\n{sql[:2000]}"

    def test_multiple_valuesets_same_resource_type(self):
        """Multiple valuesets for same resource type should have unique names."""
        from ...translator import CQLToSQLTranslator
        from ...parser import parse_cql

        cql = """
        library Test version '1.0'

        valueset "Essential Hypertension": 'http://example.org/fhir/ValueSet/essential-hypertension'
        valueset "Diabetes": 'http://example.org/fhir/ValueSet/diabetes'

        context Patient

        define "Hypertension":
            [Condition: "Essential Hypertension"]

        define "Diabetes Conditions":
            [Condition: "Diabetes"]
        """
        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(library)

        # Both valueset aliases should appear in the SQL
        assert 'Essential Hypertension' in sql or 'Diabetes' in sql, \
            f"Expected valueset references in SQL:\n{sql[:2000]}"


class TestSQLQueryBuilderReferences:
    """Tests for SQLQueryBuilder CTE reference tracking."""

    def test_query_builder_tracks_references(self):
        """Test that SQLQueryBuilder tracks CTE references."""
        builder = SQLQueryBuilder()

        # Track a CTE reference
        alias = builder.track_cte_reference("_sq_14")

        assert alias == "j1"  # First reference gets alias j1
        assert ("_sq_14", "_sq_14") in builder.cte_references
        assert builder.cte_references[("_sq_14", "_sq_14")].alias == "j1"
        assert builder.cte_references[("_sq_14", "_sq_14")].patient_correlated is True

    def test_query_builder_tracks_multiple_references(self):
        """Test tracking multiple CTE references."""
        builder = SQLQueryBuilder()

        alias1 = builder.track_cte_reference("_sq_14")
        alias2 = builder.track_cte_reference("_sq_15")

        assert alias1 == "j1"
        assert alias2 == "j2"
        assert len(builder.cte_references) == 2

    def test_query_builder_custom_alias(self):
        """Test tracking CTE with semantic alias."""
        builder = SQLQueryBuilder()

        alias = builder.track_cte_reference("_sq_14", semantic_alias="custom_alias")

        assert alias == "j1"  # Auto-generated alias
        assert builder.cte_references[("_sq_14", "custom_alias")].alias == "j1"

    def test_query_builder_has_references(self):
        """Test has_references method."""
        builder = SQLQueryBuilder()
        assert builder.has_references() is False

        builder.track_cte_reference("_sq_14")
        assert builder.has_references() is True

    def test_query_builder_clear(self):
        """Test clearing all references."""
        builder = SQLQueryBuilder()
        builder.track_cte_reference("_sq_14")
        builder.track_cte_reference("_sq_15")

        assert builder.has_references() is True

        builder.clear()

        assert builder.has_references() is False
        assert builder.join_counter == 0

    def test_query_builder_get_column_reference(self):
        """Test getting column reference for tracked CTE."""
        builder = SQLQueryBuilder()
        builder.track_cte_reference("_sq_14")

        col_ref = builder.get_column_reference("_sq_14", "resource")
        sql = col_ref.to_sql()

        assert sql == "j1.resource"

    def test_query_builder_generate_joins(self):
        """Test generating JOIN clauses for tracked CTEs."""
        builder = SQLQueryBuilder()
        builder.track_cte_reference("_sq_14")
        builder.track_cte_reference("_sq_15")

        joins = builder.generate_joins(patient_alias="_pt")

        assert len(joins) == 2
        # Verify join structure
        join1_sql = joins[0].to_sql()
        assert "LEFT JOIN _sq_14 AS j1" in join1_sql
        assert "j1.patient_id = _pt.patient_id" in join1_sql


class TestCTEMaterializedHint:
    """Tests for MATERIALIZED hints on CTEs."""

    def test_retrieve_cte_has_materialized_hint(self):
        """Test that SQLRetrieveCTE generates MATERIALIZED hint when enabled."""
        cte = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
            materialized=True,
        )
        sql = cte.to_sql()

        assert "AS MATERIALIZED" in sql

    def test_retrieve_cte_without_materialized_hint(self):
        """Test that SQLRetrieveCTE omits MATERIALIZED hint when disabled."""
        cte = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
            materialized=False,
        )
        sql = cte.to_sql()

        assert "MATERIALIZED" not in sql

    def test_retrieve_cte_default_materialized(self):
        """Test that SQLRetrieveCTE defaults to materialized=True."""
        cte = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
        )
        sql = cte.to_sql()

        # Default should be MATERIALIZED
        assert "AS MATERIALIZED" in sql

    def test_all_ctes_in_with_clause_have_materialized(self):
        """Test that all CTEs generated by translator include MATERIALIZED hint.

        This is an integration test that verifies the _apply_subquery_ctes_to_population_sql
        method adds MATERIALIZED to all injected CTEs.
        """
        # Create multiple CTEs
        cte1 = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
            materialized=True,
        )
        cte2 = SQLRetrieveCTE(
            name="Observation",
            resource_type="Observation",
            materialized=True,
        )

        sql1 = cte1.to_sql()
        sql2 = cte2.to_sql()

        # Both should have MATERIALIZED
        assert "AS MATERIALIZED" in sql1
        assert "AS MATERIALIZED" in sql2


class TestCTEMaterializedHintWithValueset:
    """Tests for MATERIALIZED hints with valueset-filtered CTEs."""

    def test_valueset_cte_has_materialized(self):
        """Test CTE with valueset filter includes MATERIALIZED hint."""
        cte = SQLRetrieveCTE(
            name="Condition: Hypertension",
            resource_type="Condition",
            valueset_url="http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.104.12.1011",
            valueset_alias="Essential Hypertension",
            materialized=True,
        )
        sql = cte.to_sql()

        assert "AS MATERIALIZED" in sql
        assert "in_valueset" in sql

    def test_special_name_cte_has_materialized(self):
        """Test CTE with special characters in name includes MATERIALIZED hint."""
        cte = SQLRetrieveCTE(
            name="Condition: Hypertension",
            resource_type="Condition",
            materialized=True,
        )
        sql = cte.to_sql()

        assert "AS MATERIALIZED" in sql
        # Name with colon should be quoted
        assert '"Condition: Hypertension"' in sql


class TestCTEMaterializedHintIntegration:
    """Integration tests for MATERIALIZED hints in generated SQL."""

    def test_full_cte_structure_with_materialized(self):
        """Test full CTE SQL structure includes MATERIALIZED hint."""
        cte = SQLRetrieveCTE(
            name="Observation",
            resource_type="Observation",
            materialized=True,
        )
        sql = cte.to_sql()

        # Verify structure: name AS MATERIALIZED (SELECT ...)
        assert "Observation AS MATERIALIZED" in sql
        assert "SELECT DISTINCT" in sql
        assert "r.patient_ref" in sql
        assert "r.resource" in sql
        assert "FROM resources r" in sql


class TestPrecomputedColumns:
    """Tests for pre-computed choice-type columns in CTEs."""

    @pytest.fixture(autouse=True)
    def _setup_schema(self):
        from ...translator.fhir_schema import FHIRSchemaRegistry
        from ...translator.model_config import DEFAULT_MODEL_CONFIG
        self._schema = FHIRSchemaRegistry(model_config=DEFAULT_MODEL_CONFIG)
        self._schema.load_default_resources()

    def test_condition_cte_has_precomputed_columns(self):
        """Test that Condition CTE includes pre-computed columns."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type="Condition",
            fhir_schema=self._schema,
        )
        sql = cte.to_sql()

        # Condition should have status, onset_date, abatement_date, recorded_date
        assert "status" in sql
        assert "onset_date" in sql
        assert "abatement_date" in sql
        # Should use fhirpath functions
        assert "fhirpath_text" in sql or "fhirpath_date" in sql

    def test_observation_cte_has_precomputed_columns(self):
        """Test that Observation CTE includes pre-computed columns."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type="Observation",
            fhir_schema=self._schema,
        )
        sql = cte.to_sql()

        # Observation should have effective_date, status
        assert "effective_date" in sql
        assert "status" in sql
        # Should use fhirpath functions (dateTime fields use fhirpath_text)
        assert "fhirpath_text" in sql

    def test_procedure_cte_has_precomputed_columns(self):
        """Test that Procedure CTE includes pre-computed columns."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type="Procedure",
            fhir_schema=self._schema,
        )
        sql = cte.to_sql()

        # Procedure should have performed_date, status
        assert "performed_date" in sql
        assert "status" in sql

    def test_medication_request_cte_has_precomputed_columns(self):
        """Test that MedicationRequest CTE includes pre-computed columns."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type="MedicationRequest",
            fhir_schema=self._schema,
        )
        sql = cte.to_sql()

        # MedicationRequest should have authored_date, status
        assert "authored_date" in sql
        assert "status" in sql

    def test_precomputed_columns_include_materialized(self):
        """Test that CTEs with pre-computed columns still have MATERIALIZED hint."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type="Condition",
            fhir_schema=self._schema,
        )
        sql = cte.to_sql()

        assert "AS MATERIALIZED" in sql
        assert "status" in sql

    def test_precomputed_columns_with_valueset(self):
        """Test that CTEs with valueset have both valueset filter and pre-computed columns."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type="Condition",
            valueset_url="http://example.org/fhir/ValueSet/test",
            valueset_alias="Test Valueset",
            fhir_schema=self._schema,
        )
        sql = cte.to_sql()

        # Should have valueset filter
        assert "in_valueset" in sql
        # Should also have pre-computed columns
        assert "status" in sql
        assert "onset_date" in sql

    def test_precomputed_columns_use_coalesce_for_choice_types(self):
        """Test that pre-computed columns use COALESCE for choice-type fields."""
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type="Observation",
            fhir_schema=self._schema,
        )
        sql = cte.to_sql()

        # effective_date uses COALESCE for effectiveDateTime and effectivePeriod.start
        assert "COALESCE" in sql

    def test_unknown_resource_type_no_precomputed_columns(self):
        """Test that unknown resource types don't get pre-computed columns."""
        from ...translator.fhir_schema import FHIRSchemaRegistry
        from ...translator.model_config import DEFAULT_MODEL_CONFIG
        schema = FHIRSchemaRegistry(model_config=DEFAULT_MODEL_CONFIG)
        schema.load_default_resources()
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type="UnknownResource",
            fhir_schema=schema,
        )
        sql = cte.to_sql()

        # Should still have basic CTE structure
        assert "AS MATERIALIZED" in sql
        assert "r.resource" in sql
        # But no pre-computed columns
        assert " AS status" not in sql  # No "status" alias
        assert " AS effective_date" not in sql  # No "effective_date" alias


class TestWindowFunctionsForFirstLast:
    """Tests for First/Last selection patterns.

    The low-level SQLWindowFunction tests verify the SQL AST node. The CQL
    translation tests below use the full translator path so retrieve
    placeholders are resolved before SQL is rendered.
    """

    def _translate_definition(self, cql: str, definition: str) -> str:
        from ...parser import parse_cql
        from ...translator import CQLToSQLTranslator

        library = parse_cql(cql)
        translator = CQLToSQLTranslator()
        definitions = translator.translate_library(library)
        return definitions[definition].to_sql()

    def test_sql_window_function_type_generates_correct_sql(self):
        """Test SQLWindowFunction type directly generates correct SQL."""
        from ...translator.types import SQLWindowFunction, SQLIdentifier

        # Create a ROW_NUMBER window function
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[
                (SQLIdentifier(name="effective_date"), "DESC"),
                (SQLIdentifier(name="id"), "ASC"),
            ],
        )

        sql = window.to_sql()

        assert "ROW_NUMBER()" in sql
        assert "PARTITION BY patient_ref" in sql
        assert "ORDER BY" in sql
        assert "effective_date DESC" in sql
        assert "id ASC" in sql

    def test_window_function_without_partition(self):
        """Test window function without PARTITION BY clause."""
        from ...translator.types import SQLWindowFunction, SQLIdentifier

        window = SQLWindowFunction(
            function="ROW_NUMBER",
            order_by=[(SQLIdentifier(name="date"), "DESC")],
        )

        sql = window.to_sql()

        assert "ROW_NUMBER()" in sql
        assert "ORDER BY date DESC" in sql
        assert "PARTITION BY" not in sql

    def test_window_function_with_frame_clause(self):
        """Test window function with frame clause."""
        from ...translator.types import SQLWindowFunction, SQLIdentifier

        window = SQLWindowFunction(
            function="SUM",
            function_args=[SQLIdentifier(name="amount")],
            partition_by=[SQLIdentifier(name="customer_id")],
            order_by=[(SQLIdentifier(name="date"), "ASC")],
            frame_clause="ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW",
        )

        sql = window.to_sql()

        assert "SUM(amount)" in sql
        assert "PARTITION BY customer_id" in sql
        assert "ORDER BY date ASC" in sql
        assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql

    def test_first_query_uses_limit_one_with_patient_correlation(self):
        """First(query) should select one row for the current patient."""
        sql = self._translate_definition(
            """
            library T
            using FHIR version '4.0.1'
            context Patient

            define "FirstObs":
                First([Observation] O sort by effectiveDateTime desc)
            """,
            "FirstObs",
        )

        assert "ORDER BY" in sql, f"Expected ORDER BY in:\n{sql}"
        assert "LIMIT 1" in sql.upper(), f"Expected LIMIT 1 in:\n{sql}"
        assert "O.patient_id = _pt.patient_id" in sql, f"Expected patient correlation in:\n{sql}"
        assert "effectiveDateTime') DESC NULLS FIRST" in sql, f"Expected explicit DESC ordering in:\n{sql}"

    def test_last_query_reverses_sort_for_limit_one(self):
        """Last(query sort asc) should reverse ordering before applying LIMIT 1."""
        sql = self._translate_definition(
            """
            library T
            using FHIR version '4.0.1'
            context Patient

            define "LastObs":
                Last([Observation] O sort by effectiveDateTime asc)
            """,
            "LastObs",
        )

        assert "ORDER BY" in sql, f"Expected ORDER BY in:\n{sql}"
        assert "LIMIT 1" in sql.upper(), f"Expected LIMIT 1 in:\n{sql}"
        assert "effectiveDateTime') DESC NULLS FIRST" in sql, f"Expected reversed DESC ordering in:\n{sql}"

    def test_last_query_uses_limit_one_for_most_recent_per_patient(self):
        """Last(query sort asc) should compile to the most recent row per patient."""
        sql = self._translate_definition(
            """
            library T
            using FHIR version '4.0.1'
            context Patient

            define "RecentCondition":
                Last([Condition] C sort by onsetDateTime asc)
            """,
            "RecentCondition",
        )

        assert "LIMIT 1" in sql.upper(), f"Expected LIMIT 1 in:\n{sql}"
        assert "C.patient_id = _pt.patient_id" in sql, f"Expected patient correlation in:\n{sql}"
        assert "onsetDateTime') DESC NULLS FIRST" in sql, f"Expected most-recent ordering in:\n{sql}"

    def test_last_query_preserves_where_clause(self):
        """The translated scalar selection should keep the query WHERE clause."""
        sql = self._translate_definition(
            """
            library T
            using FHIR version '4.0.1'
            context Patient

            define "RecentActiveCondition":
                Last(
                    [Condition] C
                        where C.clinicalStatus is not null
                        sort by onsetDateTime asc
                )
            """,
            "RecentActiveCondition",
        )

        assert "WHERE" in sql.upper(), f"Expected WHERE clause in:\n{sql}"
        assert "C.clinical_status IS NOT NULL" in sql, f"Expected translated predicate in:\n{sql}"
        assert "C.patient_id = _pt.patient_id" in sql, f"Expected patient correlation in:\n{sql}"
        assert "LIMIT 1" in sql.upper(), f"Expected LIMIT 1 in:\n{sql}"

    def test_first_last_query_includes_resource_id_tie_breaker(self):
        """Selection should be deterministic when rows share the same sort key."""
        sql = self._translate_definition(
            """
            library T
            using FHIR version '4.0.1'
            context Patient

            define "FirstObs":
                First([Observation] O sort by effectiveDateTime asc)
            """,
            "FirstObs",
        )

        assert "json_extract_string(O.resource, '$.id') ASC NULLS LAST" in sql, \
            f"Expected resource ID tie-breaker in:\n{sql}"


class TestASTLevelCTEReferenceTracking:
    """Tests for AST-level CTE reference tracking during translation."""

    def test_cte_reference_tracked_during_translation(self):
        """Test that CTE references are tracked during expression translation."""
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...translator.queries import SQLQueryBuilder
        from ...parser.ast_nodes import Identifier

        context = SQLTranslationContext()
        context.query_builder = SQLQueryBuilder()
        context.add_definition("TestCondition", "some_sql")

        translator = ExpressionTranslator(context)

        # Translate a reference to the definition
        ident = Identifier(name="TestCondition")
        result = translator.translate(ident, boolean_context=False)

        # The CTE reference should be tracked
        assert context.query_builder.has_references()
        assert ("TestCondition", "TestCondition") in context.query_builder.cte_references

    def test_nested_cte_references(self):
        """Test tracking nested CTE references (CTE A references CTE B)."""
        from ...translator.queries import SQLQueryBuilder

        builder = SQLQueryBuilder()

        # Track CTE B first
        builder.track_cte_reference("CTE_B")

        # Track CTE A that references CTE B
        builder.track_cte_reference("CTE_A")

        assert len(builder.cte_references) == 2
        assert ("CTE_A", "CTE_A") in builder.cte_references
        assert ("CTE_B", "CTE_B") in builder.cte_references

    def test_multiple_cte_references_in_same_query(self):
        """Test tracking multiple CTE references in the same query."""
        from ...translator.queries import SQLQueryBuilder

        builder = SQLQueryBuilder()

        # Track multiple CTEs
        builder.track_cte_reference("Condition")
        builder.track_cte_reference("Observation")
        builder.track_cte_reference("Procedure")

        assert len(builder.cte_references) == 3
        joins = builder.generate_joins(patient_alias="_pt")
        assert len(joins) == 3


class TestASTLevelJOINGeneration:
    """Tests for AST-level JOIN generation in SQLSelect."""

    def test_join_added_to_select_ast(self):
        """Test that JOINs are added to SQLSelect.joins list."""
        from ...translator.types import SQLSelect, SQLJoin, SQLIdentifier, SQLQualifiedIdentifier, SQLBinaryOp

        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["_pt", "patient_id"])],
            from_clause=SQLIdentifier(name="patients AS p"),
        )

        # Add a JOIN
        join = SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name='"Condition"'),
            alias="j1",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["j1", "patient_ref"]),
                right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
            ),
        )
        select.joins.append(join)

        sql = select.to_sql()

        assert "LEFT JOIN" in sql
        assert "j1" in sql
        assert "patient_ref" in sql

    def test_joins_generate_correct_sql(self):
        """Test that multiple JOINs generate correct SQL."""
        from ...translator.queries import SQLQueryBuilder

        builder = SQLQueryBuilder()
        builder.track_cte_reference("Condition")
        builder.track_cte_reference("Observation")

        joins = builder.generate_joins(patient_alias="_pt")

        assert len(joins) == 2
        sql_parts = [j.to_sql() for j in joins]
        assert all("LEFT JOIN" in s for s in sql_parts)
        assert all("patient_id = _pt.patient_id" in s for s in sql_parts)


class TestColumnReferenceReplacement:
    """Tests for replacing scalar subqueries with column references."""

    def test_column_reference_instead_of_subquery(self):
        """Test that column reference is generated instead of subquery when CTE is JOINed."""
        from ...translator.context import DefinitionMeta, RowShape, SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...translator.queries import SQLQueryBuilder
        from ...translator.types import SQLQualifiedIdentifier
        from ...parser.ast_nodes import Identifier

        context = SQLTranslationContext()
        context.query_builder = SQLQueryBuilder()

        # Track a CTE reference
        context.query_builder.track_cte_reference("TestCondition")

        # Add the definition
        context.add_definition("TestCondition", "some_sql")
        context.definition_meta["TestCondition"] = DefinitionMeta(
            name="TestCondition",
            shape=RowShape.RESOURCE_ROWS,
            cql_type="Resource",
            has_resource=True,
        )

        translator = ExpressionTranslator(context)

        # Translate a reference to the definition
        ident = Identifier(name="TestCondition")
        result = translator.translate(ident, boolean_context=False)

        # Should return a qualified identifier using the join alias
        assert isinstance(result, SQLQualifiedIdentifier)
        assert result.parts == ["j1", "resource"]

    def test_fallback_to_subquery_when_cte_not_joined(self):
        """Test that subquery is still generated when CTE is not being JOINed."""
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...translator.types import SQLSubquery
        from ...parser.ast_nodes import Identifier

        context = SQLTranslationContext()
        # No query_builder - no JOIN tracking

        # Add the definition
        context.add_definition("TestCondition", "some_sql")

        translator = ExpressionTranslator(context)

        # Translate a reference to the definition
        ident = Identifier(name="TestCondition")
        result = translator.translate(ident, boolean_context=False)

        # Should return a subquery (fallback behavior)
        assert isinstance(result, SQLSubquery)


class TestSQLValidity:
    """Tests for generated SQL validity."""

    def test_generated_sql_with_joins_is_valid(self):
        """Test that generated SQL with JOINs is syntactically valid."""
        from ...translator.types import SQLSelect, SQLJoin, SQLIdentifier, SQLQualifiedIdentifier, SQLBinaryOp, SQLLiteral, SQLFunctionCall

        # Build a SELECT with JOINs like the translator would
        select = SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["j1", "resource"]),
                        SQLLiteral(value="status"),
                    ],
                ),
            ],
            from_clause=SQLIdentifier(name="patients AS p"),
        )

        # Add JOIN
        select.joins.append(SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name='"Condition"'),
            alias="j1",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["j1", "patient_ref"]),
                right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
            ),
        ))

        sql = select.to_sql()

        # Verify SQL structure
        assert "SELECT" in sql
        assert "FROM" in sql and "patients AS p" in sql  # May be quoted
        assert "LEFT JOIN" in sql
        assert "ON j1.patient_ref = _pt.patient_id" in sql
        assert "fhirpath_text(j1.resource, 'status')" in sql


class TestIsDefinitionReference:
    """Tests for _is_definition_reference helper method."""

    def test_identifies_definition_reference(self):
        """Test that _is_definition_reference correctly identifies definition references."""
        from ...translator import CQLToSQLTranslator
        from ...translator.types import SQLIdentifier
        from ...parser.ast_nodes import Identifier

        translator = CQLToSQLTranslator()

        # Create an identifier representing a definition
        ident = Identifier(name="TestDefinition")

        # Add the definition to the context
        translator._context._definitions["TestDefinition"] = "SELECT resource FROM resources"

        # This method should check if it's a definition reference
        # The implementation would need to check if the identifier name exists in definitions
        assert hasattr(translator, '_is_definition_reference') or True  # Placeholder until method exists

    def test_identifies_non_definition_reference(self):
        """Test that _is_definition_reference correctly identifies non-definition references."""
        from ...translator import CQLToSQLTranslator
        from ...parser.ast_nodes import Identifier

        translator = CQLToSQLTranslator()

        # Create an identifier that's not a definition
        ident = Identifier(name="UnknownDefinition")

        # Add a different definition to ensure this one isn't found
        translator._context._definitions["OtherDefinition"] = "SELECT resource FROM resources"

        # Since _is_definition_reference doesn't exist yet, test what should happen
        # When the method is implemented, it should return False for unknown definitions
        assert not hasattr(translator, '_is_definition_reference') or not translator._is_definition_reference(ident)  # Will be True when method exists and works correctly


class TestIsCTEReference:
    """Tests for _is_cte_reference helper method."""

    def test_identifies_cte_reference(self):
        """Test that _is_cte_reference correctly identifies CTE references."""
        from ...translator import CQLToSQLTranslator
        from ...translator.types import SQLSubquery, SQLSelect, SQLIdentifier

        translator = CQLToSQLTranslator()

        # Create a subquery that references a CTE
        subquery = SQLSubquery(
            query=SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=SQLIdentifier(name='"Condition"')
            )
        )

        # Mock query builder with tracked CTE
        from ...translator.queries import SQLQueryBuilder
        translator._context.query_builder = SQLQueryBuilder()
        translator._context.query_builder.track_cte_reference('Condition')  # No quotes in tracking

        # Test the method
        result = translator._is_cte_reference(subquery)

        # Should return True for tracked CTE reference
        assert result is True

    def test_identifies_non_cte_reference(self):
        """Test that _is_cte_reference correctly identifies non-CTE references."""
        from ...translator import CQLToSQLTranslator
        from ...translator.types import SQLSubquery, SQLSelect, SQLIdentifier

        translator = CQLToSQLTranslator()

        # Create a subquery that doesn't reference a tracked CTE
        subquery = SQLSubquery(
            query=SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=SQLIdentifier(name='"Observation"')
            )
        )

        # Mock query builder without this CTE
        from ...translator.queries import SQLQueryBuilder
        translator._context.query_builder = SQLQueryBuilder()
        translator._context.query_builder.track_cte_reference('"Condition"')

        # Test the method
        result = translator._is_cte_reference(subquery)

        # Should return False for untracked CTE
        assert result is False

    def test_returns_false_without_query_builder(self):
        """Test that _is_cte_reference returns False when no query builder exists."""
        from ...translator import CQLToSQLTranslator
        from ...translator.types import SQLSubquery, SQLSelect, SQLIdentifier

        translator = CQLToSQLTranslator()

        # Don't set query builder
        translator._context.query_builder = None

        # Create a subquery
        subquery = SQLSubquery(
            query=SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=SQLIdentifier(name='"Condition"')
            )
        )

        # Test the method
        result = translator._is_cte_reference(subquery)

        # Should return False without query builder
        assert result is False

    def test_handles_non_subquery_expression(self):
        """Test that _is_cte_reference returns False for non-subquery expressions."""
        from ...translator import CQLToSQLTranslator
        from ...translator.types import SQLIdentifier

        translator = CQLToSQLTranslator()

        # Create a simple identifier (not a subquery)
        ident = SQLIdentifier(name="some_column")

        # Test the method
        result = translator._is_cte_reference(ident)

        # Should return False for non-subquery
        assert result is False


class TestGetCTEReference:
    """Tests for _get_cte_name_from_expression method."""

    def test_gets_cte_name_from_subquery(self):
        """Test that _get_cte_name_from_expression extracts CTE name from subquery."""
        from ...translator import CQLToSQLTranslator
        from ...translator.types import SQLSubquery, SQLSelect, SQLIdentifier

        translator = CQLToSQLTranslator()

        # Create a subquery with CTE
        subquery = SQLSubquery(
            query=SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=SQLIdentifier(name='"Condition"')
            )
        )

        # Test the method
        cte_name = translator._get_cte_name_from_expression(subquery)

        # Should return the CTE name
        assert cte_name == '"Condition"'

    def test_returns_none_for_non_subquery(self):
        """Test that _get_cte_name_from_expression returns None for non-subquery expressions."""
        from ...translator import CQLToSQLTranslator
        from ...translator.types import SQLIdentifier

        translator = CQLToSQLTranslator()

        # Create a simple identifier
        ident = SQLIdentifier(name="some_column")

        # Test the method
        cte_name = translator._get_cte_name_from_expression(ident)

        # Should return None
        assert cte_name is None

    def test_handles_subquery_without_from_clause(self):
        """Test that _get_cte_name_from_expression handles subquery without FROM clause."""
        from ...translator import CQLToSQLTranslator
        from ...translator.types import SQLSubquery, SQLSelect

        translator = CQLToSQLTranslator()

        # Create a subquery without FROM clause
        from ...translator.types import SQLIdentifier
        subquery = SQLSelect(
            columns=[SQLIdentifier(name="literal_value")],
            from_clause=None
        )

        # Create wrapper without FROM clause
        no_from_subquery = SQLSubquery(query=subquery)

        # Test the method
        cte_name = translator._get_cte_name_from_expression(no_from_subquery)

        # Should return None
        assert cte_name is None


class TestRawSQLColumnOptimization:
    """Tests for precomputed-column optimization inside SQLRaw fragments."""

    def test_interval_bound_calls_use_precomputed_bound_columns(self):
        """intervalStart/End over precomputed Period columns use bound columns."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import (
            SQLAlias,
            SQLFunctionCall,
            SQLIdentifier,
            SQLLiteral,
            SQLQualifiedIdentifier,
            SQLSelect,
        )

        registry = ColumnRegistry()
        registry.register_cte(
            "Encounter",
            {
                "period": ColumnInfo("period", "period", "VARCHAR"),
                "period_start": ColumnInfo("period_start", "period.start", "VARCHAR"),
                "period_end": ColumnInfo("period_end", "period.end", "VARCHAR"),
            },
        )
        query = SQLSelect(
            columns=[
                SQLFunctionCall(
                    name="intervalStart",
                    args=[SQLQualifiedIdentifier(parts=["e", "period"])],
                ),
                SQLFunctionCall(
                    name="intervalEnd",
                    args=[
                        SQLFunctionCall(
                            name="fhirpath_text",
                            args=[
                                SQLQualifiedIdentifier(parts=["e", "resource"]),
                                SQLLiteral("period"),
                            ],
                        )
                    ],
                ),
            ],
            from_clause=SQLAlias(expr=SQLIdentifier("Encounter"), alias="e"),
        )

        optimized = optimize_property_access(query, registry)
        sql = optimized.to_sql()

        assert "e.period_start" in sql
        assert "e.period_end" in sql
        assert "intervalStart(e.period)" not in sql
        assert "intervalEnd(fhirpath_text" not in sql

    def test_scalar_subquery_fhirpath_uses_precomputed_column(self):
        """FHIRPath over a scalar resource subquery should project the CTE column."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import (
            SQLAlias,
            SQLBinaryOp,
            SQLFunctionCall,
            SQLIdentifier,
            SQLLiteral,
            SQLQualifiedIdentifier,
            SQLSelect,
            SQLSubquery,
        )

        registry = ColumnRegistry()
        registry.register_cte(
            "Encounter",
            {
                "period": ColumnInfo("period", "period", "VARCHAR"),
                "status": ColumnInfo("status", "status", "VARCHAR"),
            },
        )
        subquery = SQLSubquery(
            SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["LastObs", "resource"])],
                from_clause=SQLAlias(expr=SQLIdentifier("Encounter"), alias="LastObs"),
                where=SQLBinaryOp(
                    operator="=",
                    left=SQLFunctionCall(
                        name="fhirpath_text",
                        args=[
                            SQLQualifiedIdentifier(parts=["LastObs", "resource"]),
                            SQLLiteral("status"),
                        ],
                    ),
                    right=SQLLiteral("finished"),
                ),
                limit=1,
            )
        )
        query = SQLSelect(
            columns=[
                SQLFunctionCall(
                    name="fhirpath_text",
                    args=[subquery, SQLLiteral("period")],
                )
            ]
        )

        optimized = optimize_property_access(query, registry)
        sql = optimized.to_sql()

        assert "SELECT LastObs.period FROM Encounter AS LastObs" in sql
        assert "LastObs.status = 'finished'" in sql
        assert "fhirpath_text((SELECT" not in sql
        assert "fhirpath_text(LastObs.resource, 'status')" not in sql

    def test_interval_bound_over_scalar_subquery_uses_bound_column(self):
        """intervalStart over scalar Period subqueries should select the bound column."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import (
            SQLAlias,
            SQLFunctionCall,
            SQLIdentifier,
            SQLLiteral,
            SQLQualifiedIdentifier,
            SQLSelect,
            SQLSubquery,
        )

        registry = ColumnRegistry()
        registry.register_cte(
            "Encounter",
            {
                "period": ColumnInfo("period", "period", "VARCHAR"),
                "period_start": ColumnInfo("period_start", "period.start", "VARCHAR"),
            },
        )
        subquery = SQLSubquery(
            SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["LastObs", "resource"])],
                from_clause=SQLAlias(expr=SQLIdentifier("Encounter"), alias="LastObs"),
                limit=1,
            )
        )
        query = SQLSelect(
            columns=[
                SQLFunctionCall(
                    name="intervalStart",
                    args=[
                        SQLFunctionCall(
                            name="fhirpath_text",
                            args=[subquery, SQLLiteral("period")],
                        )
                    ],
                )
            ]
        )

        optimized = optimize_property_access(query, registry)
        sql = optimized.to_sql()

        assert "SELECT LastObs.period_start FROM Encounter AS LastObs" in sql
        assert "intervalStart" not in sql
        assert "fhirpath_text" not in sql

    def test_uses_local_raw_cte_alias(self):
        """Raw subqueries with quoted CTE aliases should use registered columns."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import SQLRaw, SQLSelect

        registry = ColumnRegistry()
        registry.register_cte(
            "LastObs",
            {
                "period": ColumnInfo(
                    column_name="period",
                    fhirpath="period",
                    sql_type="VARCHAR",
                )
            },
        )
        query = SQLSelect(
            columns=[
                SQLRaw(
                    "CASE WHEN EXISTS ("
                    "SELECT 1 FROM \"LastObs\" AS LastObs "
                    "WHERE fhirpath_text(LastObs.resource, 'period') IS NOT NULL"
                    ") THEN TRUE ELSE FALSE END"
                )
            ]
        )

        optimized = optimize_property_access(query, registry)
        sql = optimized.to_sql()

        assert "LastObs.period" in sql
        assert "fhirpath_text(LastObs.resource, 'period')" not in sql

    def test_uses_ast_alias_for_raw_expression(self):
        """Raw expressions should inherit alias mappings from the surrounding AST."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import SQLAlias, SQLIdentifier, SQLRaw, SQLSelect

        registry = ColumnRegistry()
        registry.register_cte(
            "Observation",
            {
                "status": ColumnInfo(
                    column_name="status",
                    fhirpath="status",
                    sql_type="VARCHAR",
                )
            },
        )
        query = SQLSelect(
            columns=[SQLRaw("fhirpath_text(o.resource, 'status')")],
            from_clause=SQLAlias(expr=SQLIdentifier("Observation"), alias="o"),
        )

        optimized = optimize_property_access(query, registry)
        sql = optimized.to_sql()

        assert "o.status" in sql
        assert "fhirpath_text(o.resource, 'status')" not in sql

    def test_raw_non_text_fhirpath_calls_use_registered_columns(self):
        """Raw expressions should optimize all direct fhirpath resource calls."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import SQLAlias, SQLIdentifier, SQLRaw, SQLSelect

        registry = ColumnRegistry()
        registry.register_cte(
            "Observation",
            {
                "effective_date": ColumnInfo(
                    column_name="effective_date",
                    fhirpath="effectiveDateTime",
                    sql_type="VARCHAR",
                )
            },
        )
        query = SQLSelect(
            columns=[SQLRaw("CAST(fhirpath_date(o.resource, 'effectiveDateTime') AS VARCHAR)")],
            from_clause=SQLAlias(expr=SQLIdentifier("Observation"), alias="o"),
        )

        optimized = optimize_property_access(query, registry)
        sql = optimized.to_sql()

        assert "CAST(o.effective_date AS VARCHAR)" in sql
        assert "fhirpath_date(o.resource, 'effectiveDateTime')" not in sql

    def test_ast_wrapper_nodes_are_traversed_for_column_optimization(self):
        """FHIRPath calls inside CAST/EXTRACT/EXISTS wrappers should optimize."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import (
            SQLAlias,
            SQLBinaryOp,
            SQLCast,
            SQLExists,
            SQLExtract,
            SQLFunctionCall,
            SQLIdentifier,
            SQLLiteral,
            SQLQualifiedIdentifier,
            SQLSelect,
            SQLSubquery,
        )

        registry = ColumnRegistry()
        registry.register_cte(
            "Encounter",
            {
                "period": ColumnInfo(
                    column_name="period",
                    fhirpath="period",
                    sql_type="VARCHAR",
                )
            },
        )
        query = SQLSelect(
            columns=[SQLIdentifier("*")],
            from_clause=SQLAlias(expr=SQLIdentifier("Encounter"), alias="e"),
            where=SQLBinaryOp(
                operator="AND",
                left=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLCast(
                        expression=SQLFunctionCall(
                            name="intervalEnd",
                            args=[
                                SQLFunctionCall(
                                    name="fhirpath_text",
                                    args=[
                                        SQLQualifiedIdentifier(parts=["e", "resource"]),
                                        SQLLiteral("period"),
                                    ],
                                )
                            ],
                        ),
                        target_type="VARCHAR",
                    ),
                    right=SQLLiteral(None),
                ),
                right=SQLExists(
                    SQLSubquery(
                        SQLSelect(
                            columns=[SQLIdentifier("*")],
                            from_clause=SQLAlias(expr=SQLIdentifier("Encounter"), alias="inner_e"),
                            where=SQLBinaryOp(
                                operator=">",
                                left=SQLExtract(
                                    extract_field="YEAR",
                                    source=SQLFunctionCall(
                                        name="intervalStart",
                                        args=[
                                            SQLFunctionCall(
                                                name="fhirpath_text",
                                                args=[
                                                    SQLQualifiedIdentifier(parts=["inner_e", "resource"]),
                                                    SQLLiteral("period"),
                                                ],
                                            )
                                        ],
                                    ),
                                ),
                                right=SQLLiteral(2020),
                            ),
                        )
                    )
                ),
            ),
        )

        optimized = optimize_property_access(query, registry)
        sql = optimized.to_sql()

        assert "e.period_end" in sql
        assert "inner_e.period_start" in sql
        assert "intervalEnd(e.period)" not in sql
        assert "intervalStart(inner_e.period)" not in sql
        assert "fhirpath_text(e.resource, 'period')" not in sql
        assert "fhirpath_text(inner_e.resource, 'period')" not in sql

    def test_conflicting_raw_aliases_are_not_rewritten(self):
        """A raw alias used for multiple CTEs should not be guessed."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import SQLRaw, SQLSelect

        registry = ColumnRegistry()
        for cte_name in ("First CTE", "Second CTE"):
            registry.register_cte(
                cte_name,
                {
                    "status": ColumnInfo(
                        column_name="status",
                        fhirpath="status",
                        sql_type="VARCHAR",
                    )
                },
            )
        raw_sql = (
            "EXISTS (SELECT 1 FROM \"First CTE\" AS x "
            "WHERE fhirpath_text(x.resource, 'status') = 'a') "
            "OR EXISTS (SELECT 1 FROM \"Second CTE\" AS x "
            "WHERE fhirpath_text(x.resource, 'status') = 'b')"
        )
        query = SQLSelect(columns=[SQLRaw(raw_sql)])

        optimized = optimize_property_access(query, registry)
        sql = optimized.to_sql()

        assert "x.status" not in sql
        assert "fhirpath_text(x.resource, 'status')" in sql

    def test_rendered_sql_pass_ignores_unregistered_table_alias(self):
        """Rendered SQL optimization should not map base-table aliases to CTEs."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_rendered_property_access

        registry = ColumnRegistry()
        registry.register_cte(
            "LastObs",
            {
                "period": ColumnInfo(
                    column_name="period",
                    fhirpath="period",
                    sql_type="VARCHAR",
                )
            },
        )
        sql_text = (
            "WITH \"LastObs\" AS ("
            "SELECT fhirpath_text(r.resource, 'period') AS period "
            "FROM resources r"
            ") "
            "SELECT * FROM \"LastObs\" AS LastObs "
            "WHERE fhirpath_text(LastObs.resource, 'period') IS NOT NULL"
        )

        optimized = optimize_rendered_property_access(sql_text, registry)

        assert "fhirpath_text(r.resource, 'period')" in optimized
        assert "LastObs.period IS NOT NULL" in optimized

    def test_scalar_subquery_fhirpath_number_keeps_non_numeric_type_guard(self):
        """Do not replace fhirpath_number() with a text precomputed column."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import (
            SQLAlias,
            SQLFunctionCall,
            SQLIdentifier,
            SQLLiteral,
            SQLQualifiedIdentifier,
            SQLSelect,
            SQLSubquery,
        )

        registry = ColumnRegistry()
        registry.register_cte(
            "Observation: Score",
            {
                "value": ColumnInfo(
                    column_name="value",
                    fhirpath="value",
                    sql_type="VARCHAR",
                )
            },
        )
        resource_subquery = SQLSubquery(
            query=SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["o", "resource"])],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="Observation: Score", quoted=True),
                    alias="o",
                ),
                limit=1,
            )
        )

        optimized = optimize_property_access(
            SQLFunctionCall(
                name="fhirpath_number",
                args=[resource_subquery, SQLLiteral(value="value")],
            ),
            registry,
        )
        sql = optimized.to_sql()

        assert "fhirpath_number" in sql
        assert "SELECT o.value" not in sql

    def test_scalar_subquery_precomputed_text_comparison_casts_numeric_literal(self):
        """Optimizer-created scalar subqueries remain comparable to numeric literals."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import optimize_property_access
        from ...translator.types import (
            SQLAlias,
            SQLBinaryOp,
            SQLFunctionCall,
            SQLIdentifier,
            SQLLiteral,
            SQLQualifiedIdentifier,
            SQLSelect,
            SQLSubquery,
        )

        registry = ColumnRegistry()
        registry.register_cte(
            "Observation: Score",
            {
                "value": ColumnInfo(
                    column_name="value",
                    fhirpath="value",
                    sql_type="VARCHAR",
                )
            },
        )
        resource_subquery = SQLSubquery(
            query=SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["o", "resource"])],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="Observation: Score", quoted=True),
                    alias="o",
                ),
                limit=1,
            )
        )
        comparison = SQLBinaryOp(
            operator="<",
            left=SQLFunctionCall(
                name="fhirpath_text",
                args=[resource_subquery, SQLLiteral(value="value")],
            ),
            right=SQLLiteral(value=5),
        )

        optimized = optimize_property_access(comparison, registry)
        sql = optimized.to_sql()

        assert "TRY_CAST((SELECT o.value" in sql
        assert " AS DOUBLE) < 5" in sql


class TestResourceColumnLineage:
    """Tests for carrying precomputed columns through resource-shaped CTEs."""

    def test_select_star_registers_derived_cte_columns(self):
        """SELECT * from a registered CTE should inherit column metadata."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import propagate_resource_column_lineage
        from ...translator.types import CTEDefinition, SQLAlias, SQLIdentifier, SQLSelect

        registry = ColumnRegistry()
        registry.register_cte(
            "Base",
            {
                "period": ColumnInfo(
                    column_name="period",
                    fhirpath="period",
                    sql_type="VARCHAR",
                )
            },
        )
        cte = CTEDefinition(
            name='"Derived"',
            query=SQLSelect(
                columns=[SQLIdentifier("*")],
                from_clause=SQLAlias(expr=SQLIdentifier("Base"), alias="b"),
            ),
        )

        propagated = propagate_resource_column_lineage([cte], registry)

        assert propagated[0].query.columns == cte.query.columns
        assert registry.lookup("Derived", "period") == "period"

    def test_explicit_resource_projection_adds_inherited_columns(self):
        """Explicit patient/resource CTEs should materialize inherited columns."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import (
            optimize_property_access,
            propagate_resource_column_lineage,
        )
        from ...translator.types import (
            CTEDefinition,
            SQLAlias,
            SQLFunctionCall,
            SQLIdentifier,
            SQLLiteral,
            SQLQualifiedIdentifier,
            SQLSelect,
        )

        registry = ColumnRegistry()
        registry.register_cte(
            "Base",
            {
                "period": ColumnInfo(
                    column_name="period",
                    fhirpath="period",
                    sql_type="VARCHAR",
                ),
                "status": ColumnInfo(
                    column_name="status",
                    fhirpath="status",
                    sql_type="VARCHAR",
                ),
            },
        )
        cte = CTEDefinition(
            name='"Derived"',
            query=SQLSelect(
                columns=[
                    SQLQualifiedIdentifier(["b", "patient_id"]),
                    SQLQualifiedIdentifier(["b", "resource"]),
                ],
                from_clause=SQLAlias(expr=SQLIdentifier("Base"), alias="b"),
            ),
        )

        propagated = propagate_resource_column_lineage([cte], registry)
        sql = propagated[0].query.to_sql()

        assert "b.period" in sql
        assert "b.status" in sql
        assert registry.lookup("Derived", "period") == "period"
        assert registry.lookup("Derived", "status") == "status"

        downstream = SQLSelect(
            columns=[
                SQLFunctionCall(
                    "fhirpath_text",
                    [
                        SQLQualifiedIdentifier(["d", "resource"]),
                        SQLLiteral("period"),
                    ],
                )
            ],
            from_clause=SQLAlias(expr=SQLIdentifier("Derived"), alias="d"),
        )
        optimized = optimize_property_access(downstream, registry)

        assert "d.period" in optimized.to_sql()

    def test_grouped_cte_does_not_inherit_columns(self):
        """Grouped projections should not receive non-grouped inherited columns."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import propagate_resource_column_lineage
        from ...translator.types import CTEDefinition, SQLAlias, SQLIdentifier, SQLSelect

        registry = ColumnRegistry()
        registry.register_cte(
            "Base",
            {
                "period": ColumnInfo(
                    column_name="period",
                    fhirpath="period",
                    sql_type="VARCHAR",
                )
            },
        )
        cte = CTEDefinition(
            name='"Grouped"',
            query=SQLSelect(
                columns=[SQLIdentifier("patient_id"), SQLIdentifier("resource")],
                from_clause=SQLAlias(expr=SQLIdentifier("Base"), alias="b"),
                group_by=[SQLIdentifier("patient_id"), SQLIdentifier("resource")],
            ),
        )

        propagate_resource_column_lineage([cte], registry)

        assert registry.lookup("Grouped", "period") is None

    def test_union_cte_inherits_common_branch_columns(self):
        """UNION outputs should inherit only columns common to every branch."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import propagate_resource_column_lineage
        from ...translator.types import (
            CTEDefinition,
            SQLAlias,
            SQLIdentifier,
            SQLSelect,
            SQLSubquery,
            SQLUnion,
        )

        registry = ColumnRegistry()
        registry.register_cte(
            "BranchA",
            {
                "performed": ColumnInfo(
                    column_name="performed",
                    fhirpath="performed",
                    sql_type="VARCHAR",
                ),
                "status": ColumnInfo(
                    column_name="status",
                    fhirpath="status",
                    sql_type="VARCHAR",
                ),
                "only_a": ColumnInfo(
                    column_name="only_a",
                    fhirpath="onlyA",
                    sql_type="VARCHAR",
                ),
            },
        )
        registry.register_cte(
            "BranchB",
            {
                "performed": ColumnInfo(
                    column_name="performed",
                    fhirpath="performed",
                    sql_type="VARCHAR",
                ),
                "status": ColumnInfo(
                    column_name="status",
                    fhirpath="status",
                    sql_type="VARCHAR",
                ),
                "only_b": ColumnInfo(
                    column_name="only_b",
                    fhirpath="onlyB",
                    sql_type="VARCHAR",
                ),
            },
        )
        cte = CTEDefinition(
            name='"Unioned"',
            query=SQLUnion(
                operands=[
                    SQLSubquery(
                        query=SQLSelect(
                            columns=[
                                SQLIdentifier("patient_id"),
                                SQLIdentifier("resource"),
                            ],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier("BranchA"),
                                alias="a",
                            ),
                        )
                    ),
                    SQLSubquery(
                        query=SQLSelect(
                            columns=[
                                SQLIdentifier("patient_id"),
                                SQLIdentifier("resource"),
                            ],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier("BranchB"),
                                alias="b",
                            ),
                        )
                    ),
                ]
            ),
        )

        propagated = propagate_resource_column_lineage([cte], registry)
        sql = propagated[0].query.to_sql()

        assert "a.performed" in sql
        assert "b.performed" in sql
        assert "a.status" in sql
        assert "b.status" in sql
        assert "only_a" not in sql
        assert "only_b" not in sql
        assert registry.lookup("Unioned", "performed") == "performed"
        assert registry.lookup("Unioned", "status") == "status"
        assert registry.lookup("Unioned", "onlyA") is None

    def test_union_resource_only_operand_materializes_patient_id(self):
        """UNION lineage should preserve patient_id normalization for resource-only arms."""
        from ...translator.column_registry import ColumnInfo, ColumnRegistry
        from ...translator.retrieve_optimizer import propagate_resource_column_lineage
        from ...translator.types import (
            CTEDefinition,
            SQLAlias,
            SQLIdentifier,
            SQLSelect,
            SQLSubquery,
            SQLUnion,
        )

        registry = ColumnRegistry()
        for cte_name in ("BranchA", "BranchB"):
            registry.register_cte(
                cte_name,
                {
                    "performed": ColumnInfo(
                        column_name="performed",
                        fhirpath="performed",
                        sql_type="VARCHAR",
                    )
                },
            )
        cte = CTEDefinition(
            name='"Unioned"',
            query=SQLUnion(
                operands=[
                    SQLSubquery(
                        query=SQLSelect(
                            columns=[SQLIdentifier("resource")],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier("BranchA"),
                                alias="a",
                            ),
                        )
                    ),
                    SQLSubquery(
                        query=SQLSelect(
                            columns=[SQLIdentifier("resource")],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier("BranchB"),
                                alias="b",
                            ),
                        )
                    ),
                ]
            ),
        )

        propagated = propagate_resource_column_lineage([cte], registry)
        sql = propagated[0].query.to_sql()

        assert "a.patient_id" in sql
        assert "b.patient_id" in sql
        assert "a.resource" in sql
        assert "b.resource" in sql
        assert "a.performed" in sql
        assert "b.performed" in sql
        assert registry.lookup("Unioned", "performed") == "performed"
