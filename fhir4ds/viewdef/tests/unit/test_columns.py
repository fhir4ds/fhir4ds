"""Unit tests for column type handling.

Tests the type mapping and column expression generation
for different FHIRPath types to DuckDB UDF functions.
"""

import pytest

from ...parser import Column
from ...generator import SQLGenerator
from ...types import ColumnType
from ...errors import ValidationError


class TestTypeMapping:
    """Tests for FHIRPath type to UDF mapping."""

    def test_all_supported_types(self):
        """Test all supported types have mappings."""
        gen = SQLGenerator()

        expected_mappings = {
            "string": "fhirpath_text",
            "integer": "fhirpath_number",
            "decimal": "fhirpath_number",
            "boolean": "fhirpath_bool",
            "date": "fhirpath_text",
            "dateTime": "fhirpath_text",
            "time": "fhirpath_text",
            "code": "fhirpath_text",
            "Coding": "fhirpath_json",
            "CodeableConcept": "fhirpath_json",
        }

        for fhir_type, expected_udf in expected_mappings.items():
            assert gen._get_udf_for_type(fhir_type) == expected_udf

    def test_null_type_defaults_to_text(self):
        """Test None type defaults to fhirpath_text."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type(None) == "fhirpath_text"

    def test_unknown_type_raises(self):
        """Unknown types are rejected instead of silently becoming text."""
        gen = SQLGenerator()
        with pytest.raises(ValidationError, match="Unsupported ViewDefinition column type"):
            gen._get_udf_for_type("unknownType")
        with pytest.raises(ValidationError, match="Unsupported ViewDefinition column type"):
            gen._get_udf_for_type("custom")

    def test_full_fhir_type_uri_mapping(self):
        """Full FHIR StructureDefinition URIs map like their relative type names."""
        gen = SQLGenerator()
        assert (
            gen._get_udf_for_type("http://hl7.org/fhir/StructureDefinition/Coding")
            == "fhirpath_json"
        )
        assert (
            gen._get_udf_for_type("http://hl7.org/fhir/StructureDefinition/integer")
            == "fhirpath_number"
        )

    def test_element_id_type_mapping(self):
        """FHIR element-ID type notation maps to JSON output without type-name guards."""
        gen = SQLGenerator()
        assert gen._get_udf_for_type("Observation.referenceRange") == "fhirpath_json"
        assert (
            gen._get_udf_for_type(
                "http://hl7.org/fhir/StructureDefinition/Observation#Observation.referenceRange"
            )
            == "fhirpath_json"
        )

        col = Column(
            path="referenceRange",
            name="rr",
            type="Observation.referenceRange",
            collection=True,
        )
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath(t.resource, 'referenceRange')" in expr
        assert "type().name" not in expr


class TestNumericTypes:
    """Tests for numeric type columns."""

    def test_integer_column(self):
        """Test integer column generates fhirpath_number."""
        gen = SQLGenerator()
        col = Column(path="valueInteger", name="int_value", type="integer")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_number" in expr
        assert 'as "int_value"' in expr

    def test_decimal_column(self):
        """Test decimal column generates fhirpath_number."""
        gen = SQLGenerator()
        col = Column(path="valueDecimal", name="decimal_value", type="decimal")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_number" in expr
        assert 'as "decimal_value"' in expr


class TestBooleanType:
    """Tests for boolean type columns."""

    def test_boolean_column(self):
        """Test boolean column generates fhirpath_bool."""
        gen = SQLGenerator()
        col = Column(path="active", name="is_active", type="boolean")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_bool" in expr
        assert 'as "is_active"' in expr

    def test_boolean_column_complex_path(self):
        """Test boolean column with complex path."""
        gen = SQLGenerator()
        col = Column(path="extension.where(url='active').valueBoolean", name="is_active", type="boolean")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_bool" in expr
        # Single quotes in path are escaped (doubled) for SQL
        assert "extension.where(url=''active'').valueBoolean" in expr


class TestDateTimeTypes:
    """Tests for date/time type columns."""

    def test_date_column(self):
        """Test date column generates fhirpath_text."""
        gen = SQLGenerator()
        col = Column(path="birthDate", name="birth_date", type="date")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_text" in expr
        assert 'as "birth_date"' in expr

    def test_datetime_column(self):
        """Test dateTime column generates fhirpath_text."""
        gen = SQLGenerator()
        col = Column(path="meta.lastUpdated", name="last_updated", type="dateTime")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_text" in expr
        assert 'as "last_updated"' in expr

    def test_time_column(self):
        """Test time column generates fhirpath_text."""
        gen = SQLGenerator()
        col = Column(path="valueTime", name="time_value", type="time")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_text" in expr


class TestCodeTypes:
    """Tests for code-related type columns."""

    def test_code_column(self):
        """Test code column generates fhirpath_text."""
        gen = SQLGenerator()
        col = Column(path="status", name="status_code", type="code")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_text" in expr

    def test_coding_column(self):
        """Test Coding column generates fhirpath_json."""
        gen = SQLGenerator()
        col = Column(path="coding", name="coding_value", type="Coding")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_json" in expr

    def test_codeable_concept_column(self):
        """Test CodeableConcept column generates fhirpath_json."""
        gen = SQLGenerator()
        col = Column(path="code", name="concept", type="CodeableConcept")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "fhirpath_json" in expr


class TestMixedTypes:
    """Tests for queries with mixed column types."""

    def test_mixed_type_query(self):
        """Test query with multiple column types."""
        gen = SQLGenerator()
        columns = [
            Column(path="id", name="id", type="string"),
            Column(path="active", name="active", type="boolean"),
            Column(path="count", name="count", type="integer"),
            Column(path="code", name="code", type="CodeableConcept"),
        ]
        sql = gen.generate_columns(columns, "t.resource")

        assert "fhirpath_text" in sql  # string
        assert "fhirpath_bool" in sql  # boolean
        assert "fhirpath_number" in sql  # integer
        assert "fhirpath_json" in sql  # CodeableConcept


class TestPathEscaping:
    """Tests for FHIRPath escaping in SQL."""

    def test_path_with_single_quotes(self):
        """Test path containing single quotes is escaped."""
        gen = SQLGenerator()
        col = Column(path="name.where(use='official')", name="official_name")
        expr = gen.generate_column_expr(col, "t.resource")

        # Single quotes in path should be doubled
        assert "''official''" in expr

    def test_path_with_multiple_quotes(self):
        """Test path with multiple single quotes."""
        gen = SQLGenerator()
        col = Column(path="value = 'it's'", name="test")
        expr = gen.generate_column_expr(col, "t.resource")

        # All single quotes should be doubled
        assert "''it''s''" in expr


class TestColumnTypePreservation:
    """Tests that column type is preserved in dataclass."""

    def test_column_stores_type(self):
        """Test Column stores type correctly."""
        col = Column(path="id", name="id", type="integer")
        assert col.type == ColumnType.INTEGER

    def test_column_default_type_is_none(self):
        """Test Column type defaults to None."""
        col = Column(path="id", name="id")
        assert col.type is None

    def test_column_collection_flag(self):
        """Test Column collection flag."""
        col = Column(path="name.given", name="given_names", collection=True)
        assert col.collection is True

    def test_column_description(self):
        """Test Column description."""
        col = Column(path="id", name="id", description="Patient identifier")
        assert col.description == "Patient identifier"


class TestDirectColumnValidationPerSpecSofVd03Skeptic:
    """SOF-VD-03 SKEPTIC fresh rerun (2026-07-03).

    Direct Column dataclass construction must validate spec-defined fields
    via ``__post_init__``, matching the validation pattern used by sibling
    dataclasses ``Constant``, ``ColumnTag``, and ``Join``. SQL-on-FHIR
    requires column.path (1..1 non-empty FHIRPath), column.name (1..1
    sql-name), column.description (0..1 markdown string), and
    column.collection (boolean). Previously, direct construction deferred
    these checks to ``to_dict()`` and ``SQLGenerator._validate_column_shape``.
    """

    def test_direct_construct_rejects_empty_name(self):
        """Column(name='') must raise ValueError at construction."""
        with pytest.raises(ValueError, match="name"):
            Column(path="id", name="")

    def test_direct_construct_rejects_empty_path(self):
        """Column(path='') must raise ValueError at construction."""
        with pytest.raises(ValueError, match="path"):
            Column(path="", name="id")

    @pytest.mark.parametrize("bad_name", ["_bad", "bad-name", "bad.name", "9bad", "bad name"])
    def test_direct_construct_rejects_invalid_sql_name(self, bad_name: str):
        """All sql-name violations are rejected at construction."""
        with pytest.raises(ValueError, match="sql-name"):
            Column(path="id", name=bad_name)

    @pytest.mark.parametrize("bad_description", [5, 1.5, [], {"k": "v"}])
    def test_direct_construct_rejects_non_string_description(self, bad_description):
        """Non-string description is rejected at construction."""
        with pytest.raises(ValueError, match="description"):
            Column(path="id", name="id", description=bad_description)

    @pytest.mark.parametrize("bad_collection", ["false", "true", 0, 1, "yes"])
    def test_direct_construct_rejects_non_boolean_collection(self, bad_collection):
        """Non-boolean collection is rejected at construction."""
        with pytest.raises(ValueError, match="collection"):
            Column(path="id", name="id", collection=bad_collection)

    def test_direct_construct_accepts_valid_column(self):
        """A spec-compliant Column still constructs normally."""
        col = Column(path="id", name="patient_id")
        assert col.path == "id"
        assert col.name == "patient_id"
        assert col.collection is False
        assert col.description is None

    def test_direct_construct_accepts_optional_description(self):
        """Column(description=None) means omitted metadata."""
        col = Column(path="id", name="id", description=None)
        assert col.description is None
        # Round-trip: omitted description does not appear in to_dict().
        assert "description" not in col.to_dict()

    def test_direct_construct_round_trips_to_dict(self):
        """A directly constructed valid Column serializes correctly."""
        col = Column(
            path="id",
            name="patient_id",
            description="Patient identifier",
        )
        out = col.to_dict()
        assert out == {
            "path": "id",
            "name": "patient_id",
            "description": "Patient identifier",
        }
