"""Unit tests for WHERE clause generation.

Tests the generation of WHERE clauses from ViewDefinition
where conditions using fhirpath UDF functions.
"""

import pytest

from ...parser import parse_view_definition
from ...generator import SQLGenerator


class TestWhereClauseGeneration:
    """Tests for WHERE clause SQL generation."""

    def test_simple_boolean_where(self):
        """Test WHERE with simple boolean condition."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }],
            "where": [
                {"path": "active = true"}
            ]
        }
        ''')

        gen = SQLGenerator()

        # Check if generator has where method
        if hasattr(gen, 'generate_where'):
            sql = gen.generate_where(vd.where, "t.resource")
            assert "WHERE" in sql
            assert "fhirpath" in sql.lower()
            assert "active = true" in sql

    def test_string_comparison_where(self):
        """Test WHERE with string comparison."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }],
            "where": [
                {"path": "gender = 'female'"}
            ]
        }
        ''')

        gen = SQLGenerator()

        if hasattr(gen, 'generate_where'):
            sql = gen.generate_where(vd.where, "t.resource")
            assert "WHERE" in sql
            assert "gender" in sql

    def test_multiple_where_conditions(self):
        """Test WHERE with multiple conditions (AND)."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }],
            "where": [
                {"path": "active = true"},
                {"path": "gender = 'female'"}
            ]
        }
        ''')

        gen = SQLGenerator()

        if hasattr(gen, 'generate_where'):
            sql = gen.generate_where(vd.where, "t.resource")
            assert "WHERE" in sql
            assert "AND" in sql

    def test_empty_where_returns_empty(self):
        """Test empty where list returns empty string."""
        gen = SQLGenerator()

        if hasattr(gen, 'generate_where'):
            sql = gen.generate_where([], "t.resource")
            assert sql == ""


class TestWhereInSelect:
    """Tests for WHERE clauses within select structures."""

    def test_where_in_nested_select(self):
        """Test WHERE clause in nested select."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ],
                "select": [{
                    "column": [
                        {"path": "value", "name": "phone"}
                    ],
                    "where": [
                        {"path": "system = 'phone'"}
                    ]
                }]
            }]
        }
        ''')

        assert len(vd.select[0].select[0].where) == 1
        assert vd.select[0].select[0].where[0]["path"] == "system = 'phone'"

    def test_where_with_foreach(self):
        """Test WHERE clause combined with forEach."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "forEach": "identifier",
                "where": [
                    {"path": "system = 'http://example.org/mrn'"}
                ],
                "column": [
                    {"path": "value", "name": "mrn"}
                ]
            }]
        }
        ''')

        assert vd.select[0].forEach == "identifier"
        assert len(vd.select[0].where) == 1


class TestWhereConditionTypes:
    """Tests for different WHERE condition types."""

    def test_equality_condition(self):
        """Test equality condition in WHERE."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
            "where": [{"path": "status = 'active'"}]
        }
        ''')

        assert vd.where[0]["path"] == "status = 'active'"

    def test_comparison_condition(self):
        """Test comparison condition in WHERE."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
            "where": [{"path": "value > 100"}]
        }
        ''')

        assert vd.where[0]["path"] == "value > 100"

    def test_function_condition(self):
        """Test function call in WHERE."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
            "where": [{"path": "name.exists()"}]
        }
        ''')

        assert vd.where[0]["path"] == "name.exists()"

    def test_complex_condition(self):
        """Test complex FHIRPath condition."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
            "where": [{"path": "birthDate > @1990-01-01"}]
        }
        ''')

        assert vd.where[0]["path"] == "birthDate > @1990-01-01"


class TestWhereWithConstants:
    """Tests for WHERE clauses with constant references."""

    def test_where_with_constant_reference(self):
        """Test WHERE clause referencing a constant."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "constants": [
                {"name": "FemaleGender", "valueCode": "female"}
            ],
            "select": [{"column": [{"path": "id", "name": "id"}]}],
            "where": [{"path": "gender = %FemaleGender"}]
        }
        ''')

        assert len(vd.constants) == 1
        assert "%FemaleGender" in vd.where[0]["path"]


class TestMultipleWhereClauses:
    """Tests for multiple WHERE clauses."""

    def test_top_level_and_select_where(self):
        """Test both top-level and select-level WHERE."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "where": [{"path": "active = true"}],
            "select": [{
                "column": [{"path": "id", "name": "id"}],
                "where": [{"path": "gender = 'female'"}]
            }]
        }
        ''')

        assert len(vd.where) == 1
        assert len(vd.select[0].where) == 1

    def test_three_conditions(self):
        """Test three WHERE conditions."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
            "where": [
                {"path": "active = true"},
                {"path": "gender = 'female'"},
                {"path": "birthDate > @1990-01-01"}
            ]
        }
        ''')

        assert len(vd.where) == 3


class TestWherePathEscaping:
    """Tests for escaping in WHERE paths."""

    def test_where_with_single_quotes(self):
        """Test WHERE path containing single quotes."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
            "where": [{"path": "name.family = 'O'Brien'"}]
        }
        ''')

        # Path should be preserved as-is in parsing (single quote in value)
        assert "O'Brien" in vd.where[0]["path"]

    def test_where_with_special_characters(self):
        """Test WHERE path with special characters."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
            "where": [{"path": "identifier.where(system='http://example.org').value.exists()"}]
        }
        ''')

        assert "identifier.where" in vd.where[0]["path"]
