"""Unit tests for ViewDefinition parsing.

Tests the parser module which converts JSON ViewDefinitions
into Python dataclasses.
"""

import pytest
import json

from ...parser import (
    parse_view_definition,
    validate_view_definition,
    collect_column_names,
    load_view_definition,
    ParseError,
    Column,
    Select,
    Constant,
    Join,
    ViewDefinition,
)
from ...types import ColumnType, JoinType


class TestColumnParsing:
    """Tests for Column parsing."""

    def test_column_minimal(self):
        """Test parsing a column with minimal fields."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert len(vd.select) == 1
        assert len(vd.select[0].column) == 1

        col = vd.select[0].column[0]
        assert col.path == "id"
        assert col.name == "patient_id"
        assert col.type is None
        assert col.collection is False

    def test_column_with_type(self):
        """Test parsing a column with type hint."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "birthDate", "name": "birth_date", "type": "date"}
                ]
            }]
        }
        ''')

        col = vd.select[0].column[0]
        assert col.type == ColumnType.DATE

    def test_column_with_collection(self):
        """Test parsing a collection column."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "name.given", "name": "given_names", "collection": true}
                ]
            }]
        }
        ''')

        col = vd.select[0].column[0]
        assert col.collection is True

    def test_column_with_description(self):
        """Test parsing a column with description."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id", "description": "The patient identifier"}
                ]
            }]
        }
        ''')

        col = vd.select[0].column[0]
        assert col.description == "The patient identifier"

    def test_column_missing_path_raises_error(self):
        """Test that missing path raises ParseError."""
        with pytest.raises(ParseError) as exc_info:
            parse_view_definition('''
            {
                "resource": "Patient",
                "select": [{
                    "column": [
                        {"name": "patient_id"}
                    ]
                }]
            }
            ''')
        assert "path" in str(exc_info.value).lower()

    def test_column_missing_name_raises_error(self):
        """Test that missing name raises ParseError."""
        with pytest.raises(ParseError) as exc_info:
            parse_view_definition('''
            {
                "resource": "Patient",
                "select": [{
                    "column": [
                        {"path": "id"}
                    ]
                }]
            }
            ''')
        assert "name" in str(exc_info.value).lower()


class TestSelectParsing:
    """Tests for Select structure parsing."""

    def test_select_with_columns(self):
        """Test parsing select with multiple columns."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"},
                    {"path": "gender", "name": "gender"},
                    {"path": "birthDate", "name": "birth_date"}
                ]
            }]
        }
        ''')

        assert len(vd.select[0].column) == 3
        names = [col.name for col in vd.select[0].column]
        assert names == ["patient_id", "gender", "birth_date"]

    def test_nested_select(self):
        """Test parsing nested select structures."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ],
                "select": [{
                    "column": [
                        {"path": "name.given", "name": "given_name"}
                    ]
                }]
            }]
        }
        ''')

        assert len(vd.select[0].select) == 1
        assert vd.select[0].select[0].column[0].name == "given_name"

    def test_select_with_foreach(self):
        """Test parsing select with forEach."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [
                    {"path": "given", "name": "given_name"}
                ]
            }]
        }
        ''')

        assert vd.select[0].forEach == "name"

    def test_select_with_foreachornull(self):
        """Test parsing select with forEachOrNull."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "forEachOrNull": "telecom",
                "column": [
                    {"path": "value", "name": "contact_value"}
                ]
            }]
        }
        ''')

        assert vd.select[0].forEachOrNull == "telecom"

    def test_select_with_where(self):
        """Test parsing select with where clause."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ],
                "where": [
                    {"path": "active = true"}
                ]
            }]
        }
        ''')

        assert len(vd.select[0].where) == 1
        assert vd.select[0].where[0]["path"] == "active = true"


class TestConstantParsing:
    """Tests for Constant parsing."""

    def test_constant_value_string(self):
        """Test parsing constant with string value."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "constants": [
                {"name": "Female", "valueString": "female"}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert len(vd.constants) == 1
        assert vd.constants[0].name == "Female"
        assert vd.constants[0].value == "female"

    def test_constant_value_code(self):
        """Test parsing constant with code value."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "constants": [
                {"name": "StatusActive", "valueCode": "active"}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert vd.constants[0].value == "active"

    def test_constant_value_integer(self):
        """Test parsing constant with integer value."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "constants": [
                {"name": "MaxCount", "valueInteger": 10}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert vd.constants[0].value == 10

    def test_constant_value_boolean(self):
        """Test parsing constant with boolean value."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "constants": [
                {"name": "IsActive", "valueBoolean": true}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert vd.constants[0].value is True

    def test_constant_value_coding(self):
        """Test parsing constant with Coding value."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "constants": [
                {
                    "name": "FemaleCoding",
                    "valueCoding": {
                        "system": "http://hl7.org/fhir/gender-identity",
                        "code": "female"
                    }
                }
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert vd.constants[0].name == "FemaleCoding"
        assert vd.constants[0].value["system"] == "http://hl7.org/fhir/gender-identity"
        assert vd.constants[0].value["code"] == "female"

    def test_constant_value_codeable_concept(self):
        """Test parsing constant with CodeableConcept value."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "constants": [
                {
                    "name": "DiabetesCode",
                    "valueCodeableConcept": {
                        "coding": [
                            {"system": "http://snomed.info/sct", "code": "73211009"}
                        ]
                    }
                }
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert vd.constants[0].name == "DiabetesCode"
        assert "coding" in vd.constants[0].value


class TestJoinParsing:
    """Tests for Join parsing."""

    def test_join_minimal(self):
        """Test parsing minimal join definition."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{
                "column": [
                    {"path": "id", "name": "observation_id"}
                ]
            }],
            "joins": [
                {
                    "name": "patient",
                    "resource": "Patient"
                }
            ]
        }
        ''')

        assert len(vd.joins) == 1
        assert vd.joins[0].name == "patient"
        assert vd.joins[0].resource == "Patient"

    def test_join_with_on_conditions(self):
        """Test parsing join with on conditions."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{
                "column": [
                    {"path": "id", "name": "observation_id"}
                ]
            }],
            "joins": [
                {
                    "name": "patient",
                    "resource": "Patient",
                    "on": [
                        {"path": "subject.reference"},
                        {"path": "'Patient/' + id"}
                    ]
                }
            ]
        }
        ''')

        assert len(vd.joins[0].on) == 2

    def test_join_with_type(self):
        """Test parsing join with type specification."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{
                "column": [
                    {"path": "id", "name": "observation_id"}
                ]
            }],
            "joins": [
                {
                    "name": "patient",
                    "resource": "Patient",
                    "type": "left"
                }
            ]
        }
        ''')

        assert vd.joins[0].type == JoinType.LEFT


class TestViewDefinitionParsing:
    """Tests for complete ViewDefinition parsing."""

    def test_view_definition_resource_required(self):
        """Test that resource field is required."""
        with pytest.raises(ParseError) as exc_info:
            parse_view_definition('''
            {
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            }
            ''')
        assert "resource" in str(exc_info.value).lower()

    def test_view_definition_select_required(self):
        """Test that select field is required."""
        with pytest.raises(ParseError) as exc_info:
            parse_view_definition('''
            {
                "resource": "Patient"
            }
            ''')
        assert "select" in str(exc_info.value).lower()

    def test_view_definition_with_name(self):
        """Test parsing view definition with name."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "name": "patient_view",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert vd.name == "patient_view"

    def test_view_definition_with_description(self):
        """Test parsing view definition with description."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "description": "A view of patient demographics",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert vd.description == "A view of patient demographics"

    def test_view_definition_with_where(self):
        """Test parsing view definition with top-level where."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "where": [
                {"path": "active = true"}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert len(vd.where) == 1
        assert vd.where[0]["path"] == "active = true"

    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises ParseError."""
        with pytest.raises(ParseError):
            parse_view_definition('not valid json')

    def test_non_object_raises_error(self):
        """Test that non-object JSON raises ParseError."""
        with pytest.raises(ParseError):
            parse_view_definition('["array", "not", "object"]')


class TestValidation:
    """Tests for ViewDefinition validation."""

    def test_validate_missing_resource(self):
        """Test validation catches missing resource."""
        vd = ViewDefinition(
            resource="",
            select=[Select(column=[Column(path="id", name="id")])]
        )
        warnings = validate_view_definition(vd)
        assert any("resource" in w.lower() for w in warnings)

    def test_validate_missing_select(self):
        """Test validation catches missing select."""
        vd = ViewDefinition(resource="Patient", select=[])
        warnings = validate_view_definition(vd)
        assert any("select" in w.lower() for w in warnings)

    def test_validate_duplicate_column_names(self):
        """Test validation catches duplicate column names."""
        vd = ViewDefinition(
            resource="Patient",
            select=[
                Select(column=[Column(path="id", name="patient_id")]),
                Select(column=[Column(path="identifier.value", name="patient_id")])
            ]
        )
        warnings = validate_view_definition(vd)
        assert any("duplicate" in w.lower() for w in warnings)

    def test_validate_foreach_and_foreachornull(self):
        """Test validation catches forEach and forEachOrNull together."""
        vd = ViewDefinition(
            resource="Patient",
            select=[
                Select(
                    forEach="name",
                    forEachOrNull="telecom",
                    column=[Column(path="id", name="id")]
                )
            ]
        )
        warnings = validate_view_definition(vd)
        assert any("foreach" in w.lower() and "foreachornull" in w.lower() for w in warnings)


class TestCollectColumnNames:
    """Tests for column name collection."""

    def test_collect_simple_columns(self):
        """Test collecting column names from simple select."""
        selects = [
            Select(column=[
                Column(path="id", name="patient_id"),
                Column(path="gender", name="gender")
            ])
        ]
        names = collect_column_names(selects)
        assert names == ["patient_id", "gender"]

    def test_collect_nested_columns(self):
        """Test collecting column names from nested selects."""
        selects = [
            Select(
                column=[Column(path="id", name="patient_id")],
                select=[
                    Select(column=[Column(path="name.given", name="given_name")])
                ]
            )
        ]
        names = collect_column_names(selects)
        assert names == ["patient_id", "given_name"]


class TestLoadViewDefinition:
    """Tests for loading ViewDefinition from file."""

    def test_load_from_file(self, tmp_path):
        """Test loading ViewDefinition from a file."""
        json_content = '''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        '''
        file_path = tmp_path / "test_view.json"
        file_path.write_text(json_content)

        vd = load_view_definition(str(file_path))
        assert vd.resource == "Patient"
        assert vd.select[0].column[0].name == "patient_id"

    def test_load_nonexistent_file(self):
        """Test loading from nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_view_definition("/nonexistent/path/view.json")
