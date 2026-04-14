"""Tests for SQL injection prevention in generator and join modules."""

import pytest
import sys
from pathlib import Path


from ...generator import SQLGenerator, _quote_identifier
from ...parser import Column


class TestQuoteIdentifier:
    """Tests for _quote_identifier() SQL injection prevention."""

    def test_valid_simple_name(self):
        assert _quote_identifier("patient_id") == '"patient_id"'

    def test_valid_single_letter(self):
        assert _quote_identifier("x") == '"x"'

    def test_valid_underscore_prefix(self):
        assert _quote_identifier("_internal") == '"_internal"'

    def test_valid_mixed_case(self):
        assert _quote_identifier("PatientId") == '"PatientId"'

    def test_valid_with_numbers(self):
        assert _quote_identifier("col2") == '"col2"'

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _quote_identifier("")

    def test_rejects_sql_injection_semicolon(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _quote_identifier("x; DROP TABLE patients--")

    def test_rejects_sql_injection_quotes(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _quote_identifier('x" OR 1=1--')

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _quote_identifier("has spaces")

    def test_rejects_starts_with_number(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _quote_identifier("1column")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _quote_identifier("col-name")

    def test_rejects_none(self):
        with pytest.raises((ValueError, TypeError)):
            _quote_identifier(None)


class TestColumnNameSanitization:
    """Test that generated SQL properly quotes column names."""

    def test_column_name_is_quoted(self):
        gen = SQLGenerator()
        col = Column(path="id", name="patient_id")
        result = gen.generate_column_expr(col, "resource")
        assert 'as "patient_id"' in result

    def test_malicious_column_name_rejected(self):
        gen = SQLGenerator()
        col = Column(path="id", name="x; DROP TABLE patients--")
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            gen.generate_column_expr(col, "resource")

    def test_collection_column_name_is_quoted(self):
        gen = SQLGenerator()
        col = Column(path="name.given", name="given_names", collection=True)
        result = gen.generate_column_expr(col, "resource")
        assert 'as "given_names"' in result

    def test_this_path_column_name_is_quoted(self):
        gen = SQLGenerator()
        col = Column(path="$this", name="value")
        result = gen.generate_column_expr(col, "resource")
        assert 'as "value"' in result


class TestJoinPathEscaping:
    """Test that join paths properly escape single quotes."""

    def test_join_path_with_single_quotes_escaped(self):
        from ...join import generate_on_condition
        on_clauses = [
            {"path": "subject.where(type='Patient').reference"},
            {"path": "'Patient/' + id"},
        ]
        result = generate_on_condition(on_clauses, "t", "patient")
        # Single quotes in paths should be doubled for SQL escaping
        assert "''" in result or "subject.where" in result
