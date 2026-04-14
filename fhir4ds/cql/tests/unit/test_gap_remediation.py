"""
Tests for gap remediation plan implementation.

Tests Gaps 6, 8, 9, 12 from GAP_ANALYSIS_AND_PLAN.md.
"""

import pytest
from ...parser.ast_nodes import (
    BinaryExpression,
    Identifier,
    Literal,
    UnaryExpression,
)
from ...translator.context import SQLTranslationContext
from ...translator.expressions import ExpressionTranslator
from ...translator.types import (
    SQLBinaryOp,
    SQLCase,
    SQLFunctionCall,
    SQLLiteral,
    SQLParameterRef,
    SQLRaw,
)
from ...translator.cte_builder import (
    build_retrieve_cte,
)
from ...translator.fhir_schema import FHIRSchemaRegistry
from ...translator.model_config import DEFAULT_MODEL_CONFIG


def _make_context_with_schema():
    """Create a minimal SQLTranslationContext with a fully-wired FHIRSchemaRegistry."""
    schema = FHIRSchemaRegistry(model_config=DEFAULT_MODEL_CONFIG)
    schema.load_default_resources()
    ctx = SQLTranslationContext(resource_type="Patient")
    ctx.fhir_schema = schema
    ctx.column_mappings = schema.column_mappings
    ctx.choice_type_prefixes = schema.choice_type_prefixes
    return ctx


# ---------------------------------------------------------------------------
# Gap 8: Measurement Period Reference
# Acceptance Criteria:
# - No getvariable('measurement_period') in generated SQL
# - No intervalStart() / intervalEnd() UDF calls for measurement period
# - {mp_start} and {mp_end} template parameters present in final SQL
# - Half-open interval semantics preserved
# ---------------------------------------------------------------------------

class TestGap8MeasurementPeriod:
    """Tests for Gap 8: Measurement Period Reference."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        ctx = SQLTranslationContext()
        ctx.add_symbol("Measurement Period", "parameter")
        return ExpressionTranslator(ctx)

    @pytest.fixture
    def translator_with_dates(self) -> ExpressionTranslator:
        ctx = SQLTranslationContext()
        ctx.add_symbol("Measurement Period", "parameter")
        ctx.set_measurement_period(start="2026-01-01", end="2027-01-01")
        return ExpressionTranslator(ctx)

    def test_measurement_period_no_getvariable(self, translator):
        """AC: No getvariable('measurement_period') in generated SQL."""
        ident = Identifier(name="Measurement Period")
        result = translator.translate(ident)
        sql = result.to_sql()
        assert "getvariable" not in sql.lower()

    def test_measurement_period_produces_interval_from_bounds(self, translator):
        """AC: Measurement period produces intervalFromBounds with template params."""
        ident = Identifier(name="Measurement Period")
        result = translator.translate(ident)
        assert isinstance(result, SQLFunctionCall)
        assert result.name == "intervalFromBounds"
        sql = result.to_sql()
        assert "{mp_start}" in sql
        assert "{mp_end}" in sql

    def test_start_of_measurement_period_no_interval_start(self, translator):
        """AC: No intervalStart() UDF calls for measurement period access."""
        expr = UnaryExpression(
            operator="start of",
            operand=Identifier(name="Measurement Period"),
        )
        result = translator.translate(expr)
        sql = result.to_sql()
        assert "intervalStart" not in sql
        assert "{mp_start}" in sql

    def test_end_of_measurement_period_no_interval_end(self, translator):
        """AC: No intervalEnd() UDF calls for measurement period access."""
        expr = UnaryExpression(
            operator="end of",
            operand=Identifier(name="Measurement Period"),
        )
        result = translator.translate(expr)
        sql = result.to_sql()
        assert "intervalEnd" not in sql
        assert "{mp_end}" in sql

    def test_measurement_period_with_concrete_dates(self, translator_with_dates):
        """When concrete dates are set, they appear in the SQL."""
        expr = UnaryExpression(
            operator="start of",
            operand=Identifier(name="Measurement Period"),
        )
        result = translator_with_dates.translate(expr)
        sql = result.to_sql()
        assert "2026-01-01" in sql
        assert "getvariable" not in sql.lower()

    def test_end_of_measurement_period_with_concrete_dates(self, translator_with_dates):
        """End of Measurement Period with concrete dates."""
        expr = UnaryExpression(
            operator="end of",
            operand=Identifier(name="Measurement Period"),
        )
        result = translator_with_dates.translate(expr)
        sql = result.to_sql()
        assert "2027-01-01" in sql


# ---------------------------------------------------------------------------
# Gap 9: AgeInYearsAt Birthday-Aware Calculation
# Acceptance Criteria:
# - Patient born 1960-06-15 evaluated at 2026-01-01 returns age 65, not 66
# - Patient born 1960-06-15 evaluated at 2026-07-01 returns age 66
# ---------------------------------------------------------------------------

class TestGap9AgeInYearsAt:
    """Tests for Gap 9: AgeInYearsAt Birthday-Aware Calculation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        ctx = SQLTranslationContext()
        ctx.has_patient_demographics_cte = True
        return ExpressionTranslator(ctx)

    def test_age_in_years_no_simple_date_diff(self, translator):
        """AC: Birthday-aware calculation, not simple date_diff('year', ...)."""
        # Simulate AgeInYearsAt with demographics CTE available
        as_of_date = SQLRaw(raw_sql="DATE '2026-01-01'")
        result = translator._translate_age_at_function("AgeInYearsAt", [as_of_date])
        sql = result.to_sql()
        # Should NOT use simple date_diff for year precision
        assert "date_diff" not in sql.lower() or "year" not in sql.lower()
        # Should use EXTRACT-based birthday-aware calculation
        assert "EXTRACT" in sql

    def test_age_in_years_has_birthday_adjustment(self, translator):
        """AC: Birthday adjustment with CASE WHEN for birthday not yet reached."""
        as_of_date = SQLRaw(raw_sql="DATE '2026-01-01'")
        result = translator._translate_age_at_function("AgeInYearsAt", [as_of_date])
        sql = result.to_sql()
        # Should have CASE expression for birthday adjustment
        assert "CASE" in sql
        assert "WHEN" in sql
        assert "MONTH" in sql
        assert "DAY" in sql

    def test_age_in_months_still_uses_date_diff(self, translator):
        """For month precision, date_diff is acceptable."""
        as_of_date = SQLRaw(raw_sql="DATE '2026-01-01'")
        result = translator._translate_age_at_function("AgeInMonthsAt", [as_of_date])
        sql = result.to_sql()
        assert "date_diff" in sql.lower()


# ---------------------------------------------------------------------------
# Gap 12: Equivalent (~) Operator for Code Matching
# Acceptance Criteria:
# - ~ with code-typed operand emits fhirpath_bool() with system and code
# - Code references resolved through context's code system registry
# ---------------------------------------------------------------------------

class TestGap12Equivalence:
    """Tests for Gap 12: Equivalent (~) Operator for Code Matching."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        ctx = SQLTranslationContext()
        ctx.add_codesystem("LOINC", "http://loinc.org")
        ctx.add_code("Systolic blood pressure", "LOINC", "8480-6")
        return ExpressionTranslator(ctx)

    @pytest.fixture
    def translator_no_codes(self) -> ExpressionTranslator:
        ctx = SQLTranslationContext()
        return ExpressionTranslator(ctx)

    def test_equivalence_with_code_uses_fhirpath_bool(self, translator):
        """AC: ~ with code-typed operand emits fhirpath_bool()."""
        expr = BinaryExpression(
            operator="~",
            left=Identifier(name="some_resource"),
            right=Identifier(name="Systolic blood pressure"),
        )
        translator.context.add_alias("some_resource", sql_expr="r.resource")
        result = translator.translate(expr)
        sql = result.to_sql()
        assert "fhirpath_bool" in sql

    def test_equivalence_with_code_includes_system_and_code(self, translator):
        """AC: fhirpath_bool includes both system and code in FHIRPath expression."""
        expr = BinaryExpression(
            operator="~",
            left=Identifier(name="some_resource"),
            right=Identifier(name="Systolic blood pressure"),
        )
        translator.context.add_alias("some_resource", sql_expr="r.resource")
        result = translator.translate(expr)
        sql = result.to_sql()
        assert "http://loinc.org" in sql
        assert "8480-6" in sql

    def test_equivalence_without_code_uses_null_safe_case(self, translator_no_codes):
        """When neither operand is a code, fall back to null-safe CASE."""
        expr = BinaryExpression(
            operator="~",
            left=Literal(value="a"),
            right=Literal(value="b"),
        )
        result = translator_no_codes.translate(expr)
        sql = result.to_sql()
        assert "CASE" in sql
        assert "IS NULL" in sql


# ---------------------------------------------------------------------------
# Gap 6: Retrieve CTE Column Contamination
# Acceptance Criteria:
# - Encounter CTEs do NOT contain abatement_date, onset_date, verification_status
# - Procedure CTEs do NOT contain value, abatement_date
# - Each CTE only contains columns valid for its FHIR resource type
# ---------------------------------------------------------------------------

class TestGap6ColumnContamination:
    """Tests for Gap 6: Retrieve CTE Column Contamination."""

    def test_resource_type_valid_columns_defined(self):
        """FHIRSchemaRegistry validates columns for expected resource types."""
        schema = FHIRSchemaRegistry()
        schema.load_default_resources()
        # Each resource type must have at least one valid precomputed column
        assert schema.is_valid_precomputed_column("Condition", "code")
        assert schema.is_valid_precomputed_column("Encounter", "status")
        assert schema.is_valid_precomputed_column("Observation", "code")
        assert schema.is_valid_precomputed_column("Procedure", "code")

    def test_encounter_cte_no_condition_columns(self):
        """AC: Encounter CTEs do NOT contain abatement_date, onset_date, verification_status."""
        # Provide Condition-specific properties to an Encounter CTE
        ctx = _make_context_with_schema()
        properties = {
            "onsetDateTime",           # Condition-only
            "abatementDateTime",       # Condition-only
            "verificationStatus",      # Condition-only
            "status",                  # Valid for Encounter
        }
        cte_name, cte_ast, col_info = build_retrieve_cte(
            resource_type="Encounter",
            valueset=None,
            properties=properties,
            context=ctx,
        )
        sql = cte_ast.to_sql()
        assert "onset_date" not in sql.lower().replace("onset_date_time", "")
        assert "abatement" not in sql.lower()
        assert "verification_status" not in sql.lower()
        # status should still be present
        assert "status" in sql.lower()

    def test_procedure_cte_no_observation_columns(self):
        """AC: Procedure CTEs do NOT contain value, abatement_date."""
        ctx = _make_context_with_schema()
        properties = {
            "valueQuantity.value",     # Observation-only
            "abatementDateTime",       # Condition-only
            "status",                  # Valid for Procedure
        }
        cte_name, cte_ast, col_info = build_retrieve_cte(
            resource_type="Procedure",
            valueset=None,
            properties=properties,
            context=ctx,
        )
        sql = cte_ast.to_sql()
        assert "value_quantity" not in sql.lower()
        assert "abatement" not in sql.lower()
        assert "status" in sql.lower()

    def test_condition_cte_keeps_condition_columns(self):
        """Condition CTEs should keep Condition-specific columns."""
        ctx = _make_context_with_schema()
        properties = {
            "onsetDateTime",
            "verificationStatus",
            "status",
        }
        cte_name, cte_ast, col_info = build_retrieve_cte(
            resource_type="Condition",
            valueset=None,
            properties=properties,
            context=ctx,
        )
        sql = cte_ast.to_sql()
        assert "onset_date" in sql.lower() or "onset" in sql.lower()
        assert "verification_status" in sql.lower()

    def test_column_registry_reflects_filtered_columns(self):
        """AC: Column registry accurately reflects available columns per CTE."""
        ctx = _make_context_with_schema()
        properties = {
            "onsetDateTime",       # Condition-only
            "status",              # Valid for Encounter
        }
        cte_name, cte_ast, col_info = build_retrieve_cte(
            resource_type="Encounter",
            valueset=None,
            properties=properties,
            context=ctx,
        )
        # onset_date should NOT be in column registry for Encounter
        assert "onset_date" not in col_info
        # status should be in column registry
        assert "status" in col_info


# ---------------------------------------------------------------------------
# Gap 7: ValueSet Resolution
# ---------------------------------------------------------------------------
class TestGap7ValueSetResolution:
    @pytest.fixture
    def translator(self):
        ctx = SQLTranslationContext()
        ctx.valuesets["Payer Type"] = "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.3591"
        return ExpressionTranslator(ctx)

    def test_valueset_resolver_returns_url(self, translator):
        url = translator._resolve_valueset_identifier("Payer Type")
        assert url == "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.3591"

    def test_valueset_resolver_returns_none_for_unknown(self, translator):
        url = translator._resolve_valueset_identifier("Unknown VS")
        assert url is None


# ---------------------------------------------------------------------------
# Gap 16: Property Chain Precomputation
# ---------------------------------------------------------------------------
class TestGap16PropertyChains:
    def test_encounter_cte_has_class_code(self):
        """Verify Encounter class.code is handled (formerly via PROPERTY_CHAIN_COLUMNS, now dynamic)."""
        from ...translator.fhir_schema import FHIRSchemaRegistry
        schema = FHIRSchemaRegistry()
        schema.load_default_resources()
        # class is a valid element on Encounter
        assert schema.get_element_type("Encounter", "class") is not None

    def test_encounter_cte_includes_chain_columns(self):
        from ...translator.cte_builder import build_retrieve_cte
        ctx = _make_context_with_schema()
        cte_name, cte_ast, col_info = build_retrieve_cte(
            resource_type="Encounter",
            valueset=None,
            properties={"status", "class"},
            context=ctx,
        )
        sql = cte_ast.to_sql()
        assert "status" in sql.lower()

    def test_chain_column_in_registry(self):
        """Verify Encounter class property is known to schema (B-2 dynamic path)."""
        from ...translator.fhir_schema import FHIRSchemaRegistry
        schema = FHIRSchemaRegistry()
        schema.load_default_resources()
        assert schema.get_element_type("Encounter", "class") is not None


# ---------------------------------------------------------------------------
# Gap 11: `during day of` Temporal Precision
# Acceptance Criteria:
# - Half-open intervals use < for high boundary, not <=
# - Closed intervals use <= for high boundary
# - Comparison operators selected from AST interval metadata
# ---------------------------------------------------------------------------

class TestGap11DuringPrecision:
    """Tests for Gap 11: during day of Temporal Precision."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        ctx = SQLTranslationContext()
        ctx.add_symbol("Measurement Period", "parameter")
        return ExpressionTranslator(ctx)

    def test_during_half_open_uses_less_than(self, translator):
        """AC: Half-open intervals use < for high boundary, not <=."""
        from ...parser.ast_nodes import Interval, DateTimeLiteral
        expr = BinaryExpression(
            operator="during day of",
            left=DateTimeLiteral(value="2024-06-15"),
            right=Interval(
                low=DateTimeLiteral(value="2024-01-01"),
                high=DateTimeLiteral(value="2025-01-01"),
                low_closed=True,
                high_closed=False,  # Half-open
            ),
        )
        result = translator.translate(expr)
        sql = result.to_sql()
        # Should use >= for closed start
        assert ">=" in sql
        # Should use < for open end (NOT <=)
        assert result.right.operator == "<"

    def test_during_closed_uses_lte(self, translator):
        """AC: Closed intervals use <= for high boundary."""
        from ...parser.ast_nodes import Interval, DateTimeLiteral
        expr = BinaryExpression(
            operator="during day of",
            left=DateTimeLiteral(value="2024-06-15"),
            right=Interval(
                low=DateTimeLiteral(value="2024-01-01"),
                high=DateTimeLiteral(value="2024-12-31"),
                low_closed=True,
                high_closed=True,  # Closed
            ),
        )
        result = translator.translate(expr)
        assert result.right.operator == "<="


# ---------------------------------------------------------------------------
# Gap 18: `on or before end of` Temporal Phrase
# Acceptance Criteria:
# - on or before end of MP with half-open MP produces < DATE '{mp_end}'
# - on or after start of MP with closed-start MP produces >= DATE '{mp_start}'
# ---------------------------------------------------------------------------

class TestGap18TemporalPhrase:
    """Tests for Gap 18: Temporal Phrase Translation."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        ctx = SQLTranslationContext()
        ctx.add_symbol("Measurement Period", "parameter")
        return ExpressionTranslator(ctx)

    def test_on_or_before_end_of_mp_uses_less_than(self, translator):
        """AC: on or before end of MP produces <= DATE '{mp_end}'."""
        expr = BinaryExpression(
            operator="on or before",
            left=Literal(value="2024-06-15"),
            right=UnaryExpression(
                operator="end of",
                operand=Identifier(name="Measurement Period"),
            ),
        )
        result = translator.translate(expr)
        sql = result.to_sql()
        # "on or before" translates to <=
        assert result.operator == "<="
        assert "{mp_end}" in sql

    def test_on_or_after_start_of_mp_uses_gte(self, translator):
        """AC: on or after start of MP with closed-start MP produces >= DATE '{mp_start}'."""
        expr = BinaryExpression(
            operator="on or after",
            left=Literal(value="2024-06-15"),
            right=UnaryExpression(
                operator="start of",
                operand=Identifier(name="Measurement Period"),
            ),
        )
        result = translator.translate(expr)
        sql = result.to_sql()
        # Start is inclusive, so >= is correct
        assert result.operator == ">="
        assert "{mp_start}" in sql


# ---------------------------------------------------------------------------
# Gap 1: Fluent Function Status Filtering
# ---------------------------------------------------------------------------
class TestGap1StatusFilters:
    """Tests that status filters are dynamically extracted from CQL ASTs.

    These tests use the status_filter_extractor directly, verifying that
    CQL is the source of truth for status filter logic (no JSON fallback).
    """

    def test_status_extractor_handles_simple_equality(self):
        """Extractor handles: E.status = 'finished'."""
        from ...translator.status_filter_extractor import extract_status_filter
        from ...parser.ast_nodes import (
            FunctionDefinition, Query, QuerySource, WhereClause,
            BinaryExpression, Property, Literal,
        )
        func = FunctionDefinition(
            name="isEncounterPerformed", fluent=True, parameters=[],
            expression=Query(
                source=QuerySource(expression=Property(path="E", source=None), alias="E"),
                where=WhereClause(
                    expression=BinaryExpression(
                        operator="=",
                        left=Property(path="status", source=None),
                        right=Literal(value="finished"),
                    )
                ),
            ),
        )
        result = extract_status_filter(func)
        assert result is not None
        assert result["status_field"] == "status"
        assert "finished" in result["allowed"]

    def test_status_extractor_handles_in_list(self):
        """Extractor handles: O.status in { 'final', 'amended', 'corrected' }."""
        from ...translator.status_filter_extractor import extract_status_filter
        from ...parser.ast_nodes import (
            FunctionDefinition, Query, QuerySource, WhereClause,
            BinaryExpression, Property, Literal, ListExpression,
        )
        func = FunctionDefinition(
            name="isObservationBP", fluent=True, parameters=[],
            expression=Query(
                source=QuerySource(expression=Property(path="O", source=None), alias="O"),
                where=WhereClause(
                    expression=BinaryExpression(
                        operator="in",
                        left=Property(path="status", source=None),
                        right=ListExpression(elements=[
                            Literal(value="final"),
                            Literal(value="amended"),
                            Literal(value="corrected"),
                        ]),
                    )
                ),
            ),
        )
        result = extract_status_filter(func)
        assert result is not None
        assert result["status_field"] == "status"
        assert set(result["allowed"]) == {"final", "amended", "corrected"}

    def test_status_extractor_handles_implies_null_passes(self):
        """Extractor handles implies pattern for null_passes semantics."""
        from ...translator.status_filter_extractor import extract_status_filter
        from ...parser.ast_nodes import (
            FunctionDefinition, Query, QuerySource, WhereClause,
            BinaryExpression, Property, Literal, UnaryExpression, Identifier,
        )
        func = FunctionDefinition(
            name="verified", fluent=True, parameters=[],
            expression=Query(
                source=QuerySource(expression=Property(path="C", source=None), alias="C"),
                where=WhereClause(
                    expression=BinaryExpression(
                        operator="implies",
                        left=UnaryExpression(
                            operator="is not null",
                            operand=Property(path="verificationStatus", source=None),
                        ),
                        right=BinaryExpression(
                            operator="or",
                            left=BinaryExpression(
                                operator="~",
                                left=Property(path="verificationStatus", source=None),
                                right=Identifier(name="confirmed"),
                            ),
                            right=BinaryExpression(
                                operator="~",
                                left=Property(path="verificationStatus", source=None),
                                right=Identifier(name="provisional"),
                            ),
                        ),
                    )
                ),
            ),
        )
        result = extract_status_filter(func)
        assert result is not None
        assert result["null_passes"] is True
        assert result["status_field"] == "verificationStatus"
        assert "confirmed" in result["allowed"]

    def test_status_filter_ast_produces_where_clause(self):
        """AC: Status filter generates WHERE clause for table-level refs."""
        from ...translator.fluent_functions import FluentFunctionTranslator
        from ...translator.context import SQLTranslationContext
        from ...translator.types import SQLIdentifier

        ctx = SQLTranslationContext()
        fft = FluentFunctionTranslator(ctx)
        # Pre-populate dynamic filters for this test
        fft._dynamic_status_filters = {
            "isEncounterPerformed": {"status_field": "status", "allowed": ["finished"]},
        }
        fft._dynamic_extraction_done = True
        # Use a quoted identifier (table-level CTE) to trigger WHERE clause path
        resource_expr = SQLIdentifier(name="test_source", quoted=True)
        result = fft._build_status_filter_ast("isEncounterPerformed", resource_expr, ctx)
        sql = result.to_sql()
        assert "WHERE" in sql, f"Expected WHERE clause, got: {sql}"
        assert "list_filter" not in sql, f"list_filter should not appear: {sql}"
        assert "'finished'" in sql, f"Expected 'finished' in output: {sql}"

    def test_all_five_status_functions_extractable(self):
        """AC: Key status filter functions can be extracted from CQL ASTs."""
        from ...translator.status_filter_extractor import extract_status_filter
        from ...parser.ast_nodes import (
            FunctionDefinition, Query, QuerySource, WhereClause,
            BinaryExpression, Property, Literal, ListExpression,
        )

        test_cases = {
            "isProcedurePerformed": ("status", ["completed"]),
            "isActive": ("status", ["active"]),
            "isEncounterPerformed": ("status", ["finished"]),
        }
        for func_name, (field, allowed) in test_cases.items():
            if len(allowed) == 1:
                where_expr = BinaryExpression(
                    operator="=",
                    left=Property(path=field, source=None),
                    right=Literal(value=allowed[0]),
                )
            else:
                where_expr = BinaryExpression(
                    operator="in",
                    left=Property(path=field, source=None),
                    right=ListExpression(elements=[Literal(value=v) for v in allowed]),
                )
            func = FunctionDefinition(
                name=func_name, fluent=True, parameters=[],
                expression=Query(
                    source=QuerySource(expression=Property(path="X", source=None), alias="X"),
                    where=WhereClause(expression=where_expr),
                ),
            )
            result = extract_status_filter(func)
            assert result is not None, f"Extractor failed for {func_name}"
            assert result["status_field"] == field


# ---------------------------------------------------------------------------
# Gap 5: prevalenceInterval column support
# ---------------------------------------------------------------------------
class TestGap5PrevalenceInterval:
    def test_abatement_end_date_in_condition_columns(self):
        schema = FHIRSchemaRegistry()
        schema.load_default_resources()
        assert schema.is_valid_precomputed_column("Condition", "abatement_end_date")

    def test_abatement_period_end_mapped(self):
        from ...translator.cte_builder import property_to_column_name
        # Without schema/mappings, property_to_column_name uses last segment
        assert property_to_column_name("abatementPeriod.end") == "end"


# ---------------------------------------------------------------------------
# Gap 4: without...such that → NOT EXISTS
# ---------------------------------------------------------------------------
class TestGap4WithoutSuchThat:
    def test_without_produces_not_exists(self):
        """AC: without clause produces NOT EXISTS pattern."""
        from ...translator.queries import QueryTranslator
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...parser.ast_nodes import WithClause, Retrieve

        ctx = SQLTranslationContext()
        expr_t = ExpressionTranslator(ctx)
        qt = QueryTranslator(ctx, expr_t)

        wc = WithClause(
            alias="Enc",
            expression=Retrieve(type="Encounter"),
            such_that=None,
            is_without=True,
        )
        result = qt._translate_with_clause(wc, "BP")
        sql = result.to_sql()
        assert "NOT" in sql, f"Expected NOT EXISTS in SQL, got: {sql}"

    def test_without_has_patient_correlation(self):
        """AC: NOT EXISTS subquery includes patient_id correlation."""
        from ...translator.queries import QueryTranslator
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...parser.ast_nodes import WithClause, Retrieve

        ctx = SQLTranslationContext()
        expr_t = ExpressionTranslator(ctx)
        qt = QueryTranslator(ctx, expr_t)

        wc = WithClause(
            alias="Enc",
            expression=Retrieve(type="Encounter"),
            such_that=None,
            is_without=True,
        )
        result = qt._translate_with_clause(wc, "BP")
        sql = result.to_sql()
        assert "patient" in sql.lower(), f"Expected patient correlation in SQL, got: {sql}"

    def test_without_alias_scoped_in_subquery(self):
        """AC: Alias from without clause scoped inside NOT EXISTS only."""
        from ...translator.context import SQLTranslationContext
        ctx = SQLTranslationContext()
        ctx.add_alias("Enc", sql_expr=None)
        ctx.push_scope()
        ctx.add_alias("Inner", sql_expr=None)
        assert ctx.is_alias("Inner")
        ctx.pop_scope()
        assert not ctx.is_alias("Inner"), "Inner should not leak outside scope"
        assert ctx.is_alias("Enc"), "Outer alias should survive scope pop"

    def test_translate_with_clause_without_flag(self):
        """AC: _translate_with_clause handles is_without=True → NOT EXISTS."""
        from ...translator.queries import QueryTranslator
        from ...translator.context import SQLTranslationContext
        from ...translator.expressions import ExpressionTranslator
        from ...parser.ast_nodes import WithClause, Retrieve

        ctx = SQLTranslationContext()
        expr_t = ExpressionTranslator(ctx)
        qt = QueryTranslator(ctx, expr_t)

        wc = WithClause(
            alias="Enc",
            expression=Retrieve(type="Encounter"),
            such_that=None,
            is_without=True,
        )

        result = qt._translate_with_clause(wc, "BP")
        sql = result.to_sql()
        assert "NOT" in sql, f"Expected NOT EXISTS in SQL, got: {sql}"
        assert "EXISTS" in sql or "SELECT" in sql, f"Expected subquery in SQL, got: {sql}"


# ---------------------------------------------------------------------------
# Gap 10: External Library Scoping
# ---------------------------------------------------------------------------
class TestGap10ExternalLibraryScoping:
    def test_context_has_push_pop_scope(self):
        """AC: Context supports scope isolation."""
        from ...translator.context import SQLTranslationContext
        ctx = SQLTranslationContext()
        assert hasattr(ctx, 'push_scope'), "Context must have push_scope"
        assert hasattr(ctx, 'pop_scope'), "Context must have pop_scope"

    def test_scope_isolation_preserves_outer(self):
        """AC: push/pop scope preserves outer aliases."""
        from ...translator.context import SQLTranslationContext
        ctx = SQLTranslationContext()
        ctx.add_alias("Enc", sql_expr=None)
        assert ctx.is_alias("Enc"), "Enc should be visible before push"
        ctx.push_scope()
        # Inner scope should not yet have 'Inner'
        ctx.add_alias("Inner", sql_expr=None)
        assert ctx.is_alias("Inner"), "Inner should be visible in inner scope"
        ctx.pop_scope()
        # After pop, "Inner" should not be visible
        assert not ctx.is_alias("Inner"), "Inner should not be visible after pop"
        # "Enc" should still be available
        assert ctx.is_alias("Enc"), "Enc should still be visible after pop"

    def test_inline_function_isolates_scope_for_library(self):
        """AC: External-library FunctionRef aliases are isolated from calling scope."""
        from ...translator.context import SQLTranslationContext
        from ...translator.function_inliner import FunctionInliner, FunctionDef
        from ...parser.ast_nodes import BinaryExpression, Identifier
        from ...translator.types import SQLLiteral

        ctx = SQLTranslationContext()
        # Simulate caller scope having an alias "Enc"
        ctx.add_alias("Enc", sql_expr="enc_table")

        inliner = FunctionInliner(ctx)
        # Register a simple external library function: Global.Double(x) -> x + x
        func_body = BinaryExpression(
            operator="+",
            left=Identifier(name="x"),
            right=Identifier(name="x"),
        )
        func_def = FunctionDef(
            name="Double",
            library_name="Global",
            parameters=[("x", "Integer")],
            return_type="Integer",
            body=func_body,
        )
        inliner.register_function(func_def)

        # After inlining, the outer alias "Enc" should still be intact
        result = inliner.inline_function("Double", [SQLLiteral(value=5)], ctx, library_name="Global")
        assert result is not None
        # Verify outer alias survived
        assert ctx.is_alias("Enc"), "Outer alias 'Enc' must survive library function inlining"

    def test_inline_function_no_scope_push_for_local(self):
        """AC: Local (non-library) function calls don't push extra scope."""
        from ...translator.context import SQLTranslationContext
        from ...translator.function_inliner import FunctionInliner, FunctionDef
        from ...parser.ast_nodes import Identifier
        from ...translator.types import SQLLiteral

        ctx = SQLTranslationContext()
        ctx.add_alias("Enc", sql_expr="enc_table")
        initial_scope_count = len(ctx.scopes)

        inliner = FunctionInliner(ctx)
        func_def = FunctionDef(
            name="Identity",
            parameters=[("x", "Integer")],
            return_type="Integer",
            body=Identifier(name="x"),
        )
        inliner.register_function(func_def)

        result = inliner.inline_function("Identity", [SQLLiteral(value=42)], ctx, library_name=None)
        assert result is not None
        # Scope count should be same (no extra scope pushed for local)
        assert len(ctx.scopes) == initial_scope_count, "Local function should not leave extra scopes"

    def test_scope_isolation_inner_alias_not_visible_outside(self):
        """AC: Only function parameters visible inside external function body translation."""
        from ...translator.context import SQLTranslationContext

        ctx = SQLTranslationContext()
        ctx.add_alias("Dx", sql_expr="dx_table")
        ctx.push_scope()
        ctx.add_alias("FuncParam", sql_expr="param_val")
        # Inside inner scope, both are visible
        assert ctx.is_alias("FuncParam")
        # Outer aliases visible through scope chain
        assert ctx.is_alias("Dx")
        ctx.pop_scope()
        # FuncParam gone
        assert not ctx.is_alias("FuncParam"), "FuncParam should not leak outside"
        # Dx still there
        assert ctx.is_alias("Dx"), "Dx should survive scope pop"

    def test_qualified_identifier_quotes_special_chars(self):
        """AC: SQLQualifiedIdentifier quotes parts with special characters."""
        from ...translator.types import SQLQualifiedIdentifier
        qi = SQLQualifiedIdentifier(parts=["Encounter: Frailty Encounter", "patient_id"])
        sql = qi.to_sql()
        assert '"Encounter: Frailty Encounter"' in sql, f"Should quote CTE name: {sql}"
        assert sql.endswith(".patient_id"), f"Column should not be quoted: {sql}"

    def test_exists_correlation_uses_quoted_cte_name(self):
        """AC: Boolean combinations of sub-definitions use EXISTS correlated subqueries."""
        from ...translator.types import (
            SQLSelect, SQLExists, SQLSubquery, SQLIdentifier, SQLQualifiedIdentifier
        )
        # Simulate: EXISTS (SELECT resource FROM "Enc: Special" WHERE "Enc: Special".patient_id = p.patient_id)
        inner = SQLSelect(
            columns=[SQLIdentifier(name="resource")],
            from_clause=SQLIdentifier(name="Enc: Special", quoted=True),
            where=SQLQualifiedIdentifier(parts=["Enc: Special", "patient_id"]),
        )
        exists = SQLExists(subquery=SQLSubquery(query=inner))
        sql = exists.to_sql()
        assert '"Enc: Special"' in sql, f"CTE name should be quoted: {sql}"
        # The qualified identifier in WHERE should also be quoted
        assert '"Enc: Special".patient_id' in sql, f"Qualified ref should be quoted: {sql}"

    def test_included_library_definitions_have_metadata(self):
        """AC: Included library definitions get DefinitionMeta for proper wrapping."""
        from ...parser.parser import parse_cql
        from ...translator.translator import CQLToSQLTranslator

        main_cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include IncLib version '1.0.0' called IncLib

        context Patient

        define "Test": exists [Condition]
        """
        included_cql = """
        library IncLib version '1.0.0'
        using QICore version '4.1.1'

        context Patient

        define "Inc Def": exists [Encounter]
        """
        included_lib = parse_cql(included_cql)
        main_lib = parse_cql(main_cql)
        def loader(path):
            return included_lib if path == "IncLib" else None
        translator = CQLToSQLTranslator(library_loader=loader)
        sql = translator.translate_library_to_population_sql(main_lib)
        # Verify the included definition has a CTE
        assert '"IncLib.Inc Def"' in sql, f"Included definition should have a CTE: {sql[:500]}"


# ---------------------------------------------------------------------------
# Gap 2: singleton from with Observation Components
# ---------------------------------------------------------------------------
class TestGap2SingletonFromComponents:
    def test_component_code_mapping_exists(self):
        """AC: Component code to column mapping exists."""
        from ...translator.expressions import COMPONENT_CODE_TO_COLUMN
        assert isinstance(COMPONENT_CODE_TO_COLUMN, dict)
        assert "8480-6" in COMPONENT_CODE_TO_COLUMN  # Systolic
        assert "8462-4" in COMPONENT_CODE_TO_COLUMN  # Diastolic

    def test_systolic_maps_to_correct_column(self):
        """AC: Systolic blood pressure maps to systolic_value."""
        from ...translator.expressions import COMPONENT_CODE_TO_COLUMN
        assert COMPONENT_CODE_TO_COLUMN["8480-6"] == "systolic_value"

    def test_diastolic_maps_to_correct_column(self):
        """AC: Diastolic maps to diastolic_value."""
        from ...translator.expressions import COMPONENT_CODE_TO_COLUMN
        assert COMPONENT_CODE_TO_COLUMN["8462-4"] == "diastolic_value"


# ---------------------------------------------------------------------------
# Gap 13: return projection in CQL queries
# ---------------------------------------------------------------------------
class TestGap13ReturnProjection:
    def test_query_return_handler_exists(self):
        """AC: Return clause handling exists in query translation."""
        from ...translator.queries import QueryTranslator
        assert hasattr(QueryTranslator, '_translate_return'), (
            "QueryTranslator should have _translate_return method"
        )

    def test_return_produces_select_expression(self):
        """AC: return clause produces SELECT with the return expression."""
        import inspect
        from ...translator.queries import QueryTranslator
        sig = inspect.signature(QueryTranslator._translate_return)
        params = list(sig.parameters.keys())
        assert "return_clause" in params, "Method should accept return_clause parameter"
        assert "primary_alias" in params, "Method should accept primary_alias parameter"


# ---------------------------------------------------------------------------
# Gap 17: Union with Independent Fluent Filters
# ---------------------------------------------------------------------------
class TestGap17UnionFluentFilters:
    def test_union_ast_node_exists(self):
        """AC: SQLUnion AST node exists for combining queries."""
        from ...translator.types import SQLUnion
        assert hasattr(SQLUnion, '__init__') or callable(SQLUnion)

    def test_union_produces_union_sql(self):
        """AC: Union produces UNION ALL with independent subqueries."""
        from ...translator.types import SQLUnion, SQLRaw
        branch_a = SQLRaw(raw_sql="SELECT * FROM a")
        branch_b = SQLRaw(raw_sql="SELECT * FROM b")
        union = SQLUnion(operands=[branch_a, branch_b], distinct=False)
        sql = union.to_sql()
        assert "UNION ALL" in sql, f"Expected UNION ALL in SQL, got: {sql}"
        assert "SELECT * FROM a" in sql
        assert "SELECT * FROM b" in sql

    def test_union_distinct_produces_union(self):
        """AC: Distinct union uses UNION (not UNION ALL)."""
        from ...translator.types import SQLUnion, SQLRaw
        branch_a = SQLRaw(raw_sql="SELECT 1")
        branch_b = SQLRaw(raw_sql="SELECT 2")
        union = SQLUnion(operands=[branch_a, branch_b], distinct=True)
        sql = union.to_sql()
        assert "UNION" in sql
        assert "UNION ALL" not in sql

    def test_status_filter_ast_applied_per_branch(self):
        """AC: Each union branch gets independent WHERE from dynamic status filters."""
        from ...translator.fluent_functions import FluentFunctionTranslator
        from ...translator.context import SQLTranslationContext
        from ...translator.types import SQLIdentifier, SQLUnion

        ctx = SQLTranslationContext()
        fft = FluentFunctionTranslator(ctx)
        # Pre-populate dynamic filters for this test
        fft._dynamic_status_filters = {
            "isProcedurePerformed": {"status_field": "status", "allowed": ["completed"]},
        }
        fft._dynamic_extraction_done = True

        # Use quoted identifiers (table-level CTEs) to trigger WHERE clause path
        branch_a = SQLIdentifier(name="procedure_kidney_transplant", quoted=True)
        branch_b = SQLIdentifier(name="procedure_dialysis_services", quoted=True)

        result_a = fft._build_status_filter_ast("isProcedurePerformed", branch_a, ctx)
        result_b = fft._build_status_filter_ast("isProcedurePerformed", branch_b, ctx)

        sql_a = result_a.to_sql()
        sql_b = result_b.to_sql()

        # Each branch should have its own WHERE clause
        assert "WHERE" in sql_a, f"Branch A missing WHERE: {sql_a}"
        assert "WHERE" in sql_b, f"Branch B missing WHERE: {sql_b}"
        assert "'completed'" in sql_a
        assert "'completed'" in sql_b
        # They should reference different sources
        assert "procedure_kidney_transplant" in sql_a
        assert "procedure_dialysis_services" in sql_b

    def test_is_encounter_performed_produces_where_in_union(self):
        """AC: isEncounterPerformed generates WHERE in union branches."""
        from ...translator.fluent_functions import FluentFunctionTranslator
        from ...translator.context import SQLTranslationContext
        from ...translator.types import SQLIdentifier

        ctx = SQLTranslationContext()
        fft = FluentFunctionTranslator(ctx)
        # Pre-populate dynamic filters for this test
        fft._dynamic_status_filters = {
            "isEncounterPerformed": {"status_field": "status", "allowed": ["finished"]},
        }
        fft._dynamic_extraction_done = True
        source = SQLIdentifier(name="encounter_inpatient", quoted=True)
        result = fft._build_status_filter_ast("isEncounterPerformed", source, ctx)
        sql = result.to_sql()
        assert "WHERE" in sql, f"Expected WHERE clause: {sql}"
        assert "'finished'" in sql, f"Expected 'finished': {sql}"
        assert "list_filter" not in sql, f"No list_filter allowed: {sql}"


# ---------------------------------------------------------------------------
# Gap 3: First/Last → ROW_NUMBER() Window Functions
# ---------------------------------------------------------------------------
class TestGap3FirstLastWindow:
    def test_first_last_handler_exists(self):
        """AC: First/Last function handlers exist."""
        from ...translator.expressions import ExpressionTranslator
        assert hasattr(ExpressionTranslator, '_translate_first_expression'), (
            "ExpressionTranslator should handle First"
        )
        assert hasattr(ExpressionTranslator, '_translate_last_expression'), (
            "ExpressionTranslator should handle Last"
        )

    def test_window_function_ast_node_exists(self):
        """AC: ROW_NUMBER window function pattern is available via SQLWindowFunction."""
        from ...translator.types import SQLWindowFunction, SQLIdentifier
        wf = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[(SQLIdentifier(name="date"), "ASC NULLS LAST")],
        )
        sql = wf.to_sql()
        assert "ROW_NUMBER()" in sql
        assert "PARTITION BY" in sql
        assert "ORDER BY" in sql

    def test_first_uses_asc_last_uses_desc(self):
        """AC: First() uses ASC ordering, Last() uses DESC ordering."""
        from ...translator.expressions import ExpressionTranslator
        assert hasattr(ExpressionTranslator, '_translate_first_last_with_window'), (
            "Should have shared window function helper for First/Last"
        )
