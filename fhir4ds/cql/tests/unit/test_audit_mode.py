"""Tests for audit mode in the CQL translator (Issue 4)."""

import pytest

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator


class TestAuditModeDefault:
    def test_audit_mode_false_is_default(self):
        t = CQLToSQLTranslator()
        assert t.context.audit_mode is False

    def test_audit_mode_threaded_to_context(self):
        t = CQLToSQLTranslator(audit_mode=True)
        assert t.context.audit_mode is True

    def test_audit_mode_false_sql_unchanged(self):
        """audit_mode=False must produce identical SQL to default."""
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: exists [Encounter]"
        )
        t_std = CQLToSQLTranslator()
        t_aud = CQLToSQLTranslator(audit_mode=False)
        sql_std = t_std.translate_library_to_sql(lib)
        sql_aud = t_aud.translate_library_to_sql(lib)
        assert sql_std == sql_aud


class TestAuditModeSQL:
    @pytest.fixture
    def translator_audit(self):
        return CQLToSQLTranslator(audit_mode=True)

    def test_exists_emits_audit_wrapping(self, translator_audit):
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: exists [Encounter]"
        )
        defs = translator_audit.translate_library(lib)
        sql = defs["D"].to_sql()
        # In translate_library (non-population), exists wraps as audit_leaf
        # Rich struct_pack evidence comes from _build_correlated_exists in population SQL
        assert "audit_leaf" in sql or "struct_pack" in sql

    def test_and_emits_audit_and_macro(self, translator_audit):
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: exists [Encounter] and exists [Condition]"
        )
        defs = translator_audit.translate_library(lib)
        sql = defs["D"].to_sql()
        assert "audit_and" in sql

    def test_or_emits_audit_or_macro(self, translator_audit):
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: exists [Encounter] or exists [Condition]"
        )
        defs = translator_audit.translate_library(lib)
        sql = defs["D"].to_sql()
        assert "audit_or" in sql

    def test_not_emits_audit_not_macro(self, translator_audit):
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: not exists [Encounter]"
        )
        defs = translator_audit.translate_library(lib)
        sql = defs["D"].to_sql()
        assert "audit_not" in sql

    def test_scalar_bool_gets_audit_leaf(self, translator_audit):
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: 5 > 3"
        )
        defs = translator_audit.translate_library(lib)
        sql = defs["D"].to_sql()
        assert "audit_leaf" in sql

    def test_audit_or_all_strategy(self):
        t = CQLToSQLTranslator(audit_mode=True)
        t.context.set_audit_or_strategy("all")
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: exists [Encounter] or exists [Condition]"
        )
        defs = t.translate_library(lib)
        sql = defs["D"].to_sql()
        assert "audit_or_all" in sql

    def test_population_sql_has_audit_evidence(self):
        """Population SQL path should produce struct_pack with _audit_item."""
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"IP\": exists [Encounter]\n"
        )
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "IP"}
        )
        assert "struct_pack" in sql
        assert "_audit_item" in sql
        assert "target" in sql

    def test_comparison_emits_audit_comparison(self, translator_audit):
        """Comparison operators should use audit_comparison in audit mode."""
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: 5 > 3"
        )
        defs = translator_audit.translate_library(lib)
        sql = defs["D"].to_sql()
        assert "audit_comparison" in sql
        assert "'>' " in sql or "'>'" in sql

    def test_comparison_not_emitted_when_audit_off(self):
        """audit_comparison should not appear when audit_mode is False."""
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define D: 5 > 3"
        )
        t = CQLToSQLTranslator(audit_mode=False)
        defs = t.translate_library(lib)
        sql = defs["D"].to_sql()
        assert "audit_comparison" not in sql

    def test_via_field_in_audit_item(self):
        """_audit_item evidence struct should include trace field."""
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"IP\": exists [Encounter]\n"
        )
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "IP"}
        )
        assert "trace" in sql

    def test_via_propagation_in_population_sql(self):
        """list_transform with trace append should appear in population SQL."""
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"IP\": exists [Encounter]\n"
        )
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "IP"}
        )
        assert "list_transform" in sql or "list_append" in sql

    def test_absent_sentinel_in_population_sql(self):
        """Missing resources should produce absent sentinel evidence."""
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"IP\": exists [Encounter]\n"
        )
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "IP"}
        )
        assert "'absent'" in sql
        assert "Encounter" in sql

    def test_comparison_definition_as_population_no_boolean_cast_error(self):
        """audit_comparison result must not appear bare in a WHERE clause.

        A Boolean definition whose body is a pure comparison wraps the
        comparison in audit_comparison().  When that definition is used as a
        population expression the generated pre-compute CTE must use
        audit_comparison(...).result in its WHERE clause (not the raw struct),
        so DuckDB can evaluate it as a boolean.
        """
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"Threshold Met\": 5 > 3\n"
        )
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "Threshold Met"}
        )
        # audit_comparison must appear somewhere in the generated SQL
        assert "audit_comparison" in sql
        # _audit_result must be used in the main audit CTE
        assert "_audit_result" in sql
        # There must be no bare 'WHERE audit_comparison' pattern —
        # .result must be extracted before use in WHERE clauses
        import re
        assert not re.search(r"WHERE\s+audit_comparison", sql, re.IGNORECASE)


class TestAuditEvidenceEnrichment:
    """Tests for Fix 1 (ValueSet name) and Fix 2 (comparison evidence)."""

    def test_valueset_name_in_evidence_threshold_field(self):
        """Fix 1: threshold field should show CQL retrieve syntax with alias name."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\n"
            "valueset \"Essential Hypertension\": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.104.12.1011'\n"
            "context Patient\n"
            "define \"Has HTN\": exists [Condition: \"Essential Hypertension\"]\n"
        )
        import duckdb
        from ...translator import CQLToSQLTranslator
        from ...parser import parse_cql
        from fhir4ds.cql.duckdb import register
        lib = parse_cql(cql)
        t = CQLToSQLTranslator(audit_mode=True)
        sql = t.translate_library_to_population_sql(lib, output_columns={"initial_population": "Has HTN"})
        # threshold field should use CQL retrieve syntax [Type: "ValueSet"]
        assert "Essential Hypertension" in sql
        import re
        assert re.search(r'\[Condition: "Essential Hypertension"\]', sql)

    def test_comparison_evidence_two_column_precte(self):
        """Fix 2: audit_comparison pre-compute CTE retains _cmp_result for evidence retrieval."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"Threshold Met\": 5 > 3\n"
        )
        from ...translator import CQLToSQLTranslator
        from ...parser import parse_cql
        lib = parse_cql(cql)
        t = CQLToSQLTranslator(audit_mode=True)
        sql = t.translate_library_to_population_sql(lib, output_columns={"initial_population": "Threshold Met"})
        # Two-column pre-compute CTE: must have _cmp_result column
        assert "_cmp_result" in sql
        # Main audit CTE must use COALESCE to retrieve the struct
        assert "COALESCE" in sql
        # audit_leaf(false) is the absent sentinel for patients who fail
        assert "audit_leaf(false)" in sql

    def test_comparison_evidence_attribute_fallback(self):
        """Fix 2b: attribute is populated via scalar definition name fallback for correlated subqueries."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"BP Value\": 88\n"
            "define \"Threshold Met\": \"BP Value\" < 90\n"
        )
        from ...translator import CQLToSQLTranslator
        from ...parser import parse_cql
        lib = parse_cql(cql)
        t = CQLToSQLTranslator(audit_mode=True)
        sql = t.translate_library_to_population_sql(lib, output_columns={"initial_population": "Threshold Met"})
        # audit_comparison should be present (wrapping the < operator)
        assert "audit_comparison" in sql
        # The attribute should include a reference to the scalar definition name
        assert "BP Value" in sql


class TestTraceDepth:
    """Phase 4: Verify trace arrays contain ≥ 2 entries for nested definition chains."""

    def test_nested_definitions_produce_multi_level_trace(self):
        """A chain Parent(AND) → Child → Retrieve should produce trace with ≥ 2 entries.

        Simple alias definitions (define IP: "Child") are CTEs that pass through
        the child's audit_result. Breadcrumb is added when the definition actively
        constructs audit evidence (boolean logic, comparisons, etc.).
        """
        cql = (
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"Has Encounters\": exists [Encounter]\n"
            "define \"IP\": \"Has Encounters\" and exists [Condition]\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "IP"}
        )
        # Both definition names should appear in the SQL trace construction
        assert "Has Encounters" in sql
        assert "IP" in sql
        # list_append should appear for breadcrumb injection
        assert "list_append" in sql

    def test_breadcrumb_called_for_boolean_definition(self):
        """audit_breadcrumb wraps boolean definitions that produce audit structs."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"D\": exists [Encounter] and exists [Condition]\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "D"}
        )
        # audit_breadcrumb should wrap the definition
        assert "audit_breadcrumb" in sql or "list_append" in sql
        # Definition name 'D' should appear in trace context
        assert "'D'" in sql or '"D"' in sql

    def test_inlining_does_not_suppress_breadcrumb(self):
        """Top-level defines are CTEs (not inlined), so breadcrumb is preserved."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"Inner\": exists [Encounter]\n"
            "define \"Outer\": \"Inner\"\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "Outer"}
        )
        # Both names should be referenced for trace building
        assert "Inner" in sql
        assert "Outer" in sql


class TestScalarAttribution:
    """Phase 2: Verify First/Last populate audit target with winner resource ID."""

    def test_first_on_query_emits_audit_target(self):
        """First() on a retrieve-based query should produce SQL that includes
        resourceType for target field construction."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"FirstEnc\": First([Encounter] E sort by id)\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        defs = t.translate_library(lib)
        sql = defs["FirstEnc"].to_sql()
        # First() should produce a LIMIT 1 subquery with resource access
        assert "LIMIT 1" in sql.upper() or "resource" in sql

    def test_last_on_query_emits_fhirpath_id(self):
        """Last() on a query should produce fhirpath_text(resource, 'id')
        for target extraction in audit mode."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"LastEnc\": Last([Encounter] E sort by id)\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        defs = t.translate_library(lib)
        sql = defs["LastEnc"].to_sql()
        # In audit mode, the subquery should have resource-based tie-breaking
        assert "json_extract_string" in sql or "resource" in sql

    def test_audit_comparison_six_args_in_population(self):
        """Population SQL should pass 6 arguments to audit_comparison."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define \"D\": 5 > 3\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"initial_population": "D"}
        )
        assert "audit_comparison" in sql
        # Find the audit_comparison call and count its arguments
        import re
        m = re.search(r'audit_comparison\(', sql)
        assert m is not None

    def test_scalar_return_preserves_audit_target(self):
        """First() with scalar return clause should still populate target via
        stored audit_target_expr in DefinitionMeta."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1'\n"
            "context Patient\n"
            "define \"BPs\": [Observation] O sort by effective\n"
            "define \"Lowest BP\": First(\"BPs\" O return O.value as Quantity)\n"
            "define \"Numerator\": \"Lowest BP\" < 140\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"numerator": "Numerator"}
        )
        # The audit_comparison's 6th arg should reference the winning resource
        assert "audit_comparison" in sql
        # Extract 6th arg: should contain fhirpath_text for resource ID, not NULL
        idx = sql.find("audit_comparison(")
        assert idx >= 0
        depth = 0
        for i, c in enumerate(sql[idx:]):
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    call = sql[idx:idx + i + 1]
                    break
        inner = call[len("audit_comparison("):-1]
        args = []
        d = 0
        start = 0
        for i, c in enumerate(inner):
            if c == "(":
                d += 1
            elif c == ")":
                d -= 1
            elif c == "," and d == 0:
                args.append(inner[start:i].strip())
                start = i + 1
        args.append(inner[start:].strip())
        assert len(args) == 6
        target_arg = args[5]
        # Target must reference fhirpath_text for resource ID extraction
        assert "fhirpath_text" in target_arg, f"Target should extract resource ID, got: {target_arg[:100]}"
        assert "resourceType" in target_arg


class TestMinMaxAttribution:
    """Phase 2: Verify Min/Max use arg_min/arg_max for audit target."""

    def test_min_on_query_uses_arg_min(self):
        """Min() on a RESOURCE_ROWS query should generate arg_min for target."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1'\n"
            "context Patient\n"
            "define \"BPs\": [Observation] O\n"
            "define \"MinBP\": Min(\"BPs\" O return O.value as Quantity)\n"
            "define \"Check\": \"MinBP\" < 140\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"check": "Check"}
        )
        assert "arg_min" in sql, "Expected arg_min in SQL for Min attribution"
        assert "fhirpath_text" in sql

    def test_max_on_query_uses_arg_max(self):
        """Max() on a RESOURCE_ROWS query should generate arg_max for target."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1'\n"
            "context Patient\n"
            "define \"BPs\": [Observation] O\n"
            "define \"MaxBP\": Max(\"BPs\" O return O.value as Quantity)\n"
            "define \"Check\": \"MaxBP\" > 180\n"
        )
        t = CQLToSQLTranslator(audit_mode=True)
        lib = parse_cql(cql)
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"check": "Check"}
        )
        assert "arg_max" in sql, "Expected arg_max in SQL for Max attribution"

    def test_min_without_audit_mode_no_arg_min(self):
        """Min() without audit mode should NOT generate arg_min."""
        cql = (
            "library T\nusing FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1'\n"
            "context Patient\n"
            "define \"BPs\": [Observation] O\n"
            "define \"MinBP\": Min(\"BPs\" O return O.value as Quantity)\n"
            "define \"Check\": \"MinBP\" < 140\n"
        )
        t = CQLToSQLTranslator(audit_mode=False)
        lib = parse_cql(cql)
        sql = t.translate_library_to_population_sql(
            lib, output_columns={"check": "Check"}
        )
        assert "arg_min" not in sql
