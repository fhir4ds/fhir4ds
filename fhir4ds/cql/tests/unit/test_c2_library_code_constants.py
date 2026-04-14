"""
Tests for Task C2: Replace _LIBRARY_CODE_CONSTANTS with dynamic extraction.

These tests verify that code constants are extracted dynamically from parsed
library ASTs and that the translator handles missing definitions gracefully.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestLibraryCodeConstantResolution:
    """Test dynamic resolution of library code constants."""

    def test_resolve_from_context_codes(self):
        """Code constants should be resolved from context.codes (populated from AST)."""
        from ...translator.expressions import _resolve_library_code_constant

        # Mock context with codes populated
        context = MagicMock()
        context.codes = {
            "active": {"code": "active", "system": "http://hl7.org/fhir/issue-status"},
            "confirmed": {"code": "confirmed", "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status"},
        }

        # Should resolve from context.codes
        result = _resolve_library_code_constant("QICoreCommon", "active", context=context)
        assert result == "active"

        result = _resolve_library_code_constant("QICoreCommon", "confirmed", context=context)
        assert result == "confirmed"

    def test_resolve_from_included_library_ast(self):
        """Code constants should be resolved from included library ASTs."""
        from ...translator.expressions import _resolve_library_code_constant

        # Mock code definition
        mock_code = MagicMock()
        mock_code.name = "ambulatory"
        mock_code.code = "AMB"

        # Mock library AST with codes
        mock_lib_ast = MagicMock()
        mock_lib_ast.codes = [mock_code]

        # Mock library info
        mock_lib_info = MagicMock()
        mock_lib_info.library_ast = mock_lib_ast

        # Mock context
        context = MagicMock()
        context.codes = {}  # Empty current library codes
        context.includes = {"QICoreCommon": mock_lib_info}

        # Should resolve from included library AST
        result = _resolve_library_code_constant("QICoreCommon", "ambulatory", context=context)
        assert result == "AMB"

    def test_context_override_resolution(self):
        """Codes with overrides in context.codes should resolve to their configured values."""
        from ...translator.expressions import _resolve_library_code_constant

        context = MagicMock()
        context.codes = {
            "ambulatory": {"code": "AMB", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode"},
            "Birthdate": {"code": "21112-8", "system": "http://loinc.org"},
        }
        context.includes = {}

        result = _resolve_library_code_constant("QICoreCommon", "ambulatory", context=context)
        assert result == "AMB"  # Name is "ambulatory" but constant value is "AMB"

        result = _resolve_library_code_constant("QICoreCommon", "Birthdate", context=context)
        assert result == "21112-8"  # LOINC code

    def test_identity_fallback(self):
        """Without context, _resolve_library_code_constant returns None (no identity fallback)."""
        from ...translator.expressions import _resolve_library_code_constant

        # No context — returns None; caller handles non-code references
        result = _resolve_library_code_constant("QICoreCommon", "active", context=None)
        assert result is None

        result = _resolve_library_code_constant("QICoreCommon", "SomeCode", context=None)
        assert result is None

    def test_graceful_fallback_for_unknown_library(self):
        """Unknown library without context returns None."""
        from ...translator.expressions import _resolve_library_code_constant

        result = _resolve_library_code_constant("UnknownLibrary", "SomeCode", context=None)
        assert result is None


class TestQICoreCommonCodeConstants:
    """Test dynamic extraction of QICoreCommon code constants.

    These tests verify that at least 5 QICoreCommon constants are resolved correctly.
    """

    @pytest.fixture
    def mock_qicore_context(self):
        """Create a mock context with QICoreCommon code definitions."""
        context = MagicMock()
        context.codes = {
            # Well-known QICoreCommon codes
            "active": {"code": "active", "system": "http://hl7.org/fhir/issue-status"},
            "completed": {"code": "completed", "system": "http://hl7.org/fhir/task-status"},
            "finished": {"code": "finished", "system": "http://hl7.org/fhir/encounter-status"},
            "confirmed": {"code": "confirmed", "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status"},
            "provisional": {"code": "provisional", "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status"},
        }
        context.includes = {}
        return context

    def test_qicore_active_constant(self, mock_qicore_context):
        """QICoreCommon 'active' code constant."""
        from ...translator.expressions import _resolve_library_code_constant

        result = _resolve_library_code_constant("QICoreCommon", "active", context=mock_qicore_context)
        assert result == "active"

    def test_qicore_completed_constant(self, mock_qicore_context):
        """QICoreCommon 'completed' code constant."""
        from ...translator.expressions import _resolve_library_code_constant

        result = _resolve_library_code_constant("QICoreCommon", "completed", context=mock_qicore_context)
        assert result == "completed"

    def test_qicore_finished_constant(self, mock_qicore_context):
        """QICoreCommon 'finished' code constant (for encounters)."""
        from ...translator.expressions import _resolve_library_code_constant

        result = _resolve_library_code_constant("QICoreCommon", "finished", context=mock_qicore_context)
        assert result == "finished"

    def test_qicore_confirmed_constant(self, mock_qicore_context):
        """QICoreCommon 'confirmed' code constant (for verification status)."""
        from ...translator.expressions import _resolve_library_code_constant

        result = _resolve_library_code_constant("QICoreCommon", "confirmed", context=mock_qicore_context)
        assert result == "confirmed"

    def test_qicore_provisional_constant(self, mock_qicore_context):
        """QICoreCommon 'provisional' code constant (for verification status)."""
        from ...translator.expressions import _resolve_library_code_constant

        result = _resolve_library_code_constant("QICoreCommon", "provisional", context=mock_qicore_context)
        assert result == "provisional"
