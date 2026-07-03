"""Tests for SQL injection prevention in generator and join modules."""

import pytest
import sys
from pathlib import Path
import duckdb


from ...generator import SQLGenerator, _quote_identifier, _quote_table_reference
from ...errors import ValidationError
from ...parser import Column, parse_view_definition


def _assert_generated_sql_does_not_execute_injection(view_definition, source_table="resources"):
    import fhir4ds

    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        fhir4ds.register(con)
        con.execute("CREATE TABLE resources (resource JSON)")
        con.execute("INSERT INTO resources VALUES (?)", ['{"resourceType":"Patient","id":"p1","gender":"male"}'])
        con.execute("CREATE TABLE sentinel (id INTEGER)")
        try:
            sql = fhir4ds.generate_view_sql(view_definition, source_table=source_table)
        except ValidationError:
            assert con.execute("SELECT COUNT(*) FROM sentinel").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 1
            return
        try:
            con.execute(sql).fetchall()
        except duckdb.Error:
            pass
        assert con.execute("SELECT COUNT(*) FROM sentinel").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 1
    finally:
        con.close()


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
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            _quote_identifier("")

    def test_rejects_sql_injection_semicolon(self):
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            _quote_identifier("x; DROP TABLE patients--")

    def test_rejects_sql_injection_quotes(self):
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            _quote_identifier('x" OR 1=1--')

    def test_rejects_spaces(self):
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            _quote_identifier("has spaces")

    def test_rejects_starts_with_number(self):
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            _quote_identifier("1column")

    def test_rejects_special_chars(self):
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            _quote_identifier("col-name")

    def test_rejects_none(self):
        with pytest.raises((ValidationError, TypeError)):
            _quote_identifier(None)


class TestSourceTableSanitization:
    """Test that user-supplied source_table values cannot inject SQL."""

    def test_simple_source_table_is_quoted(self):
        assert _quote_table_reference("resources") == '"resources"'

    def test_schema_qualified_source_table_is_quoted(self):
        assert _quote_table_reference("main.resources") == '"main"."resources"'

    def test_malicious_source_table_rejected(self):
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            _quote_table_reference("resources; DROP TABLE resources; --")

    def test_generate_rejects_malicious_source_table(self):
        gen = SQLGenerator(source_table="resources; DROP TABLE resources; --")
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
        })
        with pytest.raises(ValidationError, match="Invalid SQL identifier"):
            gen.generate(vd)


class TestViewDefinitionInjectionRegression:
    """Generated SQL must keep FHIRPath strings inside SQL literals."""

    def test_column_path_injection_does_not_execute(self):
        _assert_generated_sql_does_not_execute_injection({
            "resource": "Patient",
            "select": [{
                "column": [{
                    "path": "id') as \"id\" FROM resources; DROP TABLE sentinel; --",
                    "name": "id",
                }],
            }],
        })

    def test_where_path_injection_does_not_execute(self):
        _assert_generated_sql_does_not_execute_injection({
            "resource": "Patient",
            "where": [{"path": "gender = 'male'') OR (''1'' = ''1"}],
            "select": [{"column": [{"path": "id", "name": "id"}]}],
        })

    def test_foreach_path_injection_does_not_execute(self):
        _assert_generated_sql_does_not_execute_injection({
            "resource": "Patient",
            "select": [{
                "forEach": "name; DROP TABLE sentinel; --",
                "column": [{"path": "$this", "name": "name"}],
            }],
        })

    def test_repeat_path_injection_does_not_execute(self):
        _assert_generated_sql_does_not_execute_injection({
            "resource": "Patient",
            "select": [{
                "repeat": ["name; DROP TABLE sentinel; --"],
                "column": [{"path": "$this", "name": "name"}],
            }],
        })


class TestColumnNameSanitization:
    """Test that generated SQL properly quotes column names."""

    def test_column_name_is_quoted(self):
        gen = SQLGenerator()
        col = Column(path="id", name="patient_id")
        result = gen.generate_column_expr(col, "resource")
        assert 'as "patient_id"' in result

    def test_malicious_column_name_rejected(self):
        # SOF-VD-03 SKEPTIC fix (2026-07-03): Column.__post_init__ now
        # enforces sql-name at construction time, so malicious names are
        # rejected before reaching the generator boundary.
        with pytest.raises(ValueError, match="sql-name"):
            Column(path="id", name="x; DROP TABLE patients--")

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
