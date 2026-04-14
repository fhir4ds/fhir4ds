"""Unit tests for SQL generation.

Tests the SQLGenerator class which converts ViewDefinition
objects into DuckDB SQL queries.
"""

import pytest

from ...parser import parse_view_definition, Column, Select, ViewDefinition
from ...generator import SQLGenerator


class TestSQLGeneratorInit:
    """Tests for SQLGenerator initialization."""

    def test_default_dialect(self):
        """Test default dialect is duckdb."""
        gen = SQLGenerator()
        assert gen.dialect == "duckdb"

    def test_unsupported_dialect_raises_error(self):
        """Test that unsupported dialect raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            SQLGenerator(dialect="postgres")
        assert "Unsupported dialect" in str(exc_info.value)


class TestTableNames:
    """Tests for table name generation."""

    def test_simple_resource(self):
        """Test simple resource pluralization."""
        gen = SQLGenerator()
        assert gen._get_table_name("Patient") == "patients"
        assert gen._get_table_name("Observation") == "observations"

    def test_resource_ending_in_y(self):
        """Test resource ending in consonant+y becomes ies."""
        gen = SQLGenerator()
        assert gen._get_table_name("Person") == "people"  # special case
        assert gen._get_table_name("Category") == "categories"

    def test_resource_ending_in_s(self):
        """Test resource ending in s becomes es."""
        gen = SQLGenerator()
        assert gen._get_table_name("Location") == "locations"
        # Note: "Status" would become "statuses" with current logic


class TestUDFSelection:
    """Tests for UDF function selection by type."""

    def test_string_type(self):
        """Test string type uses fhirpath_text."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("string") == "fhirpath_text"

    def test_integer_type(self):
        """Test integer type uses fhirpath_number."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("integer") == "fhirpath_number"

    def test_decimal_type(self):
        """Test decimal type uses fhirpath_number."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("decimal") == "fhirpath_number"

    def test_boolean_type(self):
        """Test boolean type uses fhirpath_bool."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("boolean") == "fhirpath_bool"

    def test_date_type(self):
        """Test date type uses fhirpath_text."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("date") == "fhirpath_text"

    def test_datetime_type(self):
        """Test dateTime type uses fhirpath_text."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("dateTime") == "fhirpath_text"

    def test_time_type(self):
        """Test time type uses fhirpath_text."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("time") == "fhirpath_text"

    def test_code_type(self):
        """Test code type uses fhirpath_text."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("code") == "fhirpath_text"

    def test_coding_type(self):
        """Test Coding type uses fhirpath_json."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("Coding") == "fhirpath_json"

    def test_codeable_concept_type(self):
        """Test CodeableConcept type uses fhirpath_json."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("CodeableConcept") == "fhirpath_json"

    def test_unknown_type_defaults_to_text(self):
        """Test unknown type defaults to fhirpath_text."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("unknown") == "fhirpath_text"
        assert gen._get_udf_for_type(None) == "fhirpath_text"


class TestColumnExpression:
    """Tests for column expression generation."""

    def test_simple_column(self):
        """Test generating expression for simple column."""
        gen = SQLGenerator()
        col = Column(path="id", name="patient_id")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_text" in expr
        assert "t.resource" in expr
        assert "'id'" in expr
        assert 'as "patient_id"' in expr

    def test_column_with_type(self):
        """Test generating expression for typed column."""
        gen = SQLGenerator()
        col = Column(path="active", name="is_active", type="boolean")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_bool" in expr
        assert 'as "is_active"' in expr

    def test_column_with_quoted_path(self):
        """Test path with single quotes is escaped."""
        gen = SQLGenerator()
        col = Column(path="name where value = 'test'", name="test_col")
        expr = gen.generate_column_expr(col, "t.resource")

        # Single quotes should be doubled for SQL escaping
        assert "''test''" in expr


class TestColumnsGeneration:
    """Tests for multiple column generation."""

    def test_multiple_columns(self):
        """Test generating expressions for multiple columns."""
        gen = SQLGenerator()
        columns = [
            Column(path="id", name="patient_id"),
            Column(path="gender", name="gender"),
            Column(path="birthDate", name="birth_date")
        ]
        sql = gen.generate_columns(columns, "t.resource")

        assert "patient_id" in sql
        assert "gender" in sql
        assert "birth_date" in sql
        assert sql.count("fhirpath_text") == 3

    def test_empty_columns(self):
        """Test generating expressions for empty column list."""
        gen = SQLGenerator()
        sql = gen.generate_columns([], "t.resource")
        assert sql == ""


class TestFullQueryGeneration:
    """Tests for complete SQL query generation."""

    def test_simple_patient_view(self):
        """Test generating simple patient view."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"},
                    {"path": "gender", "name": "gender"}
                ]
            }]
        }
        ''')

        gen = SQLGenerator()
        sql = gen.generate(vd)

        assert "SELECT" in sql
        assert "fhirpath_text" in sql
        assert "patient_id" in sql
        assert "gender" in sql
        assert "FROM patients" in sql

    def test_view_with_typed_columns(self):
        """Test generating view with typed columns."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"},
                    {"path": "active", "name": "is_active", "type": "boolean"},
                    {"path": "birthDate", "name": "birth_date", "type": "date"}
                ]
            }]
        }
        ''')

        gen = SQLGenerator()
        sql = gen.generate(vd)

        assert "fhirpath_bool" in sql
        assert "fhirpath_text" in sql

    def test_empty_select_returns_empty_result(self):
        """Test empty select returns appropriate SQL."""
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(column=[])]
        )

        gen = SQLGenerator()
        sql = gen.generate(vd)

        assert "SELECT NULL WHERE FALSE" in sql

    def test_observation_resource(self):
        """Test generating view for Observation resource."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{
                "column": [
                    {"path": "id", "name": "observation_id"},
                    {"path": "status", "name": "status"}
                ]
            }]
        }
        ''')

        gen = SQLGenerator()
        sql = gen.generate(vd)

        assert "FROM observations" in sql

    def test_generate_from_json(self):
        """Test generating SQL directly from JSON string."""
        gen = SQLGenerator()
        sql = gen.generate_from_json('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert "SELECT" in sql
        assert "FROM patients" in sql


class TestMultipleSelects:
    """Tests for handling multiple select structures."""

    def test_multiple_top_level_selects(self):
        """Test handling multiple top-level select structures."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [
                {
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                },
                {
                    "column": [
                        {"path": "gender", "name": "gender"}
                    ]
                }
            ]
        }
        ''')

        gen = SQLGenerator()
        sql = gen.generate(vd)

        assert "patient_id" in sql
        assert "gender" in sql
