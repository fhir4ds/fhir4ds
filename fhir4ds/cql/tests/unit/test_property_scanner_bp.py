"""
Unit tests for BP component.where() pattern detection.

Tests the helper functions for detecting and parsing FHIRPath
component.where() patterns used in blood pressure component extraction.

The functions were moved from property_scanner to column_generation.
extract_loinc_code_from_component_where and get_bp_column_name_for_loinc_code
were replaced by resolve_component_column_name which maps full FHIRPath
expressions to column names via configuration.
"""

from ...translator.column_generation import (
    is_component_where_pattern,
    resolve_component_column_name,
)


class TestIsComponentWherePattern:
    """Tests for is_component_where_pattern function."""

    def test_detects_systolic_pattern(self):
        """Should detect systolic BP component.where pattern."""
        path = "component.where(code.coding.exists(code = '8480-6')).valueQuantity.value"
        assert is_component_where_pattern(path) is True

    def test_detects_diastolic_pattern(self):
        """Should detect diastolic BP component.where pattern."""
        path = "component.where(code.coding.exists(code = '8462-4')).valueQuantity.value"
        assert is_component_where_pattern(path) is True

    def test_detects_display_pattern(self):
        """Should detect component.where with display matching."""
        path = "component.where(code.display = 'Systolic blood pressure').valueQuantity.value"
        assert is_component_where_pattern(path) is True

    def test_rejects_simple_property(self):
        """Should reject simple property paths."""
        assert is_component_where_pattern("onsetDateTime") is False
        assert is_component_where_pattern("effectiveDateTime") is False
        assert is_component_where_pattern("status") is False

    def test_rejects_nested_property(self):
        """Should reject nested property paths without where."""
        assert is_component_where_pattern("verificationStatus.coding.code") is False
        assert is_component_where_pattern("code.coding.code") is False

    def test_rejects_empty_string(self):
        """Should reject empty string."""
        assert is_component_where_pattern("") is False


class TestResolveComponentColumnName:
    """Tests for resolve_component_column_name function."""

    def test_resolves_systolic_column(self):
        """Should resolve systolic BP fhirpath to systolic_value."""
        path = "component.where(code.coding.exists(code = '8480-6')).valueQuantity.value"
        assert resolve_component_column_name(path) == "systolic_value"

    def test_resolves_diastolic_column(self):
        """Should resolve diastolic BP fhirpath to diastolic_value."""
        path = "component.where(code.coding.exists(code = '8462-4')).valueQuantity.value"
        assert resolve_component_column_name(path) == "diastolic_value"

    def test_returns_none_for_display_match(self):
        """Should return None for display-based matching (not in config)."""
        path = "component.where(code.display = 'Systolic blood pressure').valueQuantity.value"
        assert resolve_component_column_name(path) is None

    def test_returns_none_for_non_component(self):
        """Should return None for non-component paths."""
        assert resolve_component_column_name("onsetDateTime") is None
        assert resolve_component_column_name("") is None

    def test_returns_none_for_unknown_code(self):
        """Should return None for component.where with unknown LOINC code."""
        path = "component.where(code.coding.exists(code = '1234-5')).valueQuantity.value"
        assert resolve_component_column_name(path) is None


class TestIntegration:
    """Integration tests for BP pattern detection workflow."""

    def test_full_workflow_systolic(self):
        """Test full workflow for systolic pattern detection."""
        path = "component.where(code.coding.exists(code = '8480-6')).valueQuantity.value"

        # Step 1: Check it's a component.where pattern
        assert is_component_where_pattern(path) is True

        # Step 2: Resolve to column name
        column_name = resolve_component_column_name(path)
        assert column_name == "systolic_value"

    def test_full_workflow_diastolic(self):
        """Test full workflow for diastolic pattern detection."""
        path = "component.where(code.coding.exists(code = '8462-4')).valueQuantity.value"

        assert is_component_where_pattern(path) is True
        column_name = resolve_component_column_name(path)
        assert column_name == "diastolic_value"

    def test_non_bp_component_where(self):
        """Test that non-BP component.where patterns are handled gracefully."""
        path = "component.where(code.coding.exists(code = '1234-5')).valueQuantity.value"

        assert is_component_where_pattern(path) is True
        column_name = resolve_component_column_name(path)
        # No precomputed column for this code
        assert column_name is None
