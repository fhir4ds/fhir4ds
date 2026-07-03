"""Unit tests for SQL generation.

Tests the SQLGenerator class which converts ViewDefinition
objects into DuckDB SQL queries.
"""

import pytest

from ...parser import parse_view_definition, Column, Constant, Select, ViewDefinition
from ...generator import SQLGenerator
from ...errors import ParseError, ValidationError
from ...metadata import SHAREABLE_VIEWDEFINITION_PROFILE, TABULAR_VIEWDEFINITION_PROFILE
from ...types import ColumnTag


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

    def test_generate_revalidates_direct_column_tag_objects(self):
        """Direct generator boundaries reject mutated invalid ColumnTag objects."""
        tag = ColumnTag("ansi/type", "DATE")
        tag.value = None
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(column=[Column(path="id", name="id", tag=[tag])])],
        )

        with pytest.raises(ValidationError, match="Column.tag.value"):
            SQLGenerator().generate(vd)


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
        assert gen._get_table_name("SupplyDelivery") == "supplydeliveries"

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

    def test_unknown_type_raises(self):
        """Unknown column types fail fast instead of silently becoming text."""
        gen = SQLGenerator()
        with pytest.raises(ValidationError, match="Unsupported ViewDefinition column type"):
            gen._get_udf_for_type("unknown")
        assert gen._get_udf_for_type(None) == "fhirpath_text"

    def test_full_fhir_structure_definition_uri_type(self):
        """Core FHIR StructureDefinition URIs normalize to supported type behavior."""
        gen = SQLGenerator()
        assert (
            gen._get_udf_for_type("http://hl7.org/fhir/StructureDefinition/CodeableConcept")
            == "fhirpath_json"
        )
        assert (
            gen._get_udf_for_type("http://hl7.org/fhir/StructureDefinition/HumanName")
            == "fhirpath_json"
        )
        assert (
            gen._get_udf_for_type("http://hl7.org/fhir/StructureDefinition/string")
            == "fhirpath_text"
        )


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

    def test_direct_column_path_must_not_be_empty(self):
        """Direct dataclass construction rejects empty column.path.

        SOF-VD-03 SKEPTIC fix (2026-07-03): Column.__post_init__ now
        enforces non-empty path at construction time. The generator
        boundary remains, but invalid Columns cannot be constructed.
        """
        with pytest.raises(ValueError, match="path"):
            Column(path="", name="id")

    def test_direct_column_collection_must_be_boolean(self):
        """Direct dataclass construction rejects non-boolean collection.

        SOF-VD-03 SKEPTIC fix (2026-07-03): Column.__post_init__ now
        enforces boolean collection at construction time.
        """
        with pytest.raises(ValueError, match="collection"):
            Column(path="id", name="id", collection="false")

    def test_direct_column_tag_must_be_structured(self):
        """Direct dataclass construction cannot bypass tag shape checks."""
        gen = SQLGenerator()
        col = Column(path="id", name="id", tag=[{"name": "ansi/type", "value": "VARCHAR"}])
        expr = gen.generate_column_expr(col, "t.resource")
        assert 'as "id"' in expr

        col.tag = ["bad"]
        with pytest.raises(ValidationError, match="tag"):
            gen.generate_column_expr(col, "t.resource")

    def test_scalar_column_expression_has_runtime_cardinality_guard(self):
        """Generated scalar columns report multi-value runtime violations."""
        gen = SQLGenerator()
        col = Column(path="name.family", name="family", type="string")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "array_length(fhirpath(t.resource, 'name.family')) > 1" in expr
        assert "error('ViewDefinition column" in expr

    def test_typed_column_expression_has_runtime_type_guard(self):
        """Generated typed columns report runtime type mismatch violations."""
        gen = SQLGenerator()
        col = Column(path="gender", name="gender_as_int", type="integer")
        expr = gen.generate_column_expr(col, "t.resource")

        assert "(gender).type().name" in expr
        assert "'integer'" in expr
        assert "error('ViewDefinition column" in expr


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

    def test_direct_view_definition_select_must_be_non_empty(self):
        """Generator rejects direct dataclass bypass of root select cardinality."""
        vd = ViewDefinition(resource="Patient", select=[])

        with pytest.raises(ValidationError, match="select.*non-empty"):
            SQLGenerator().generate(vd)

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

    def test_direct_view_definition_resource_must_be_single_string(self):
        """Generator rejects direct dataclass bypass of the resource cardinality."""
        vd = ViewDefinition(
            resource=["Patient", "Observation"],
            select=[Select(column=[Column(path="id", name="id")])],
        )

        with pytest.raises(ValidationError, match="single FHIR ResourceType string"):
            SQLGenerator().generate(vd)

    def test_direct_view_definition_resource_must_be_known_resource_type(self):
        """Generator validates the required ResourceType binding."""
        vd = ViewDefinition(
            resource="NotARealFHIRResource",
            select=[Select(column=[Column(path="id", name="id")])],
        )

        with pytest.raises(ValidationError, match="ResourceType"):
            SQLGenerator().generate(vd)

    def test_direct_view_definition_name_must_be_sql_name(self):
        """Generator rejects direct dataclass bypass of ViewDefinition.name."""
        vd = ViewDefinition(
            resource="Patient",
            name="_bad",
            select=[Select(column=[Column(path="id", name="id")])],
        )

        with pytest.raises(ValidationError, match="sql-name"):
            SQLGenerator().generate(vd)

    def test_direct_view_definition_fhir_version_must_use_binding(self):
        """Generator validates direct dataclass fhirVersion binding values."""
        vd = ViewDefinition(
            resource="Patient",
            fhirVersion=["9.9.9"],
            select=[Select(column=[Column(path="id", name="id")])],
        )

        with pytest.raises(ValidationError, match="FHIRVersion"):
            SQLGenerator().generate(vd)

    @pytest.mark.parametrize(
        "profile",
        [
            "http://example.org/StructureDefinition/not-an-array",
            None,
            [""],
            [123],
            ["not a canonical with spaces"],
        ],
    )
    def test_direct_view_definition_profile_must_be_canonical_array(self, profile):
        """Generator validates direct dataclass profile cardinality and canonical shape."""
        vd = ViewDefinition(
            resource="Patient",
            profile=profile,
            select=[Select(column=[Column(path="id", name="id")])],
        )

        with pytest.raises(ValidationError, match="profile|canonical"):
            SQLGenerator().generate(vd)

    def test_direct_view_definition_supported_profiles_are_validated(self):
        """Generator validates profile constraints for direct dataclass construction."""
        missing_status = ViewDefinition(
            resource="Patient",
            meta={"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
            url="https://example.org/ViewDefinition/shareable",
            name="shareable_patient",
            fhirVersion=["4.0.1"],
            select=[Select(column=[Column(path="id", name="id", type="id")])],
        )
        with pytest.raises(ValidationError, match="ViewDefinition.status"):
            SQLGenerator().generate(missing_status)

        shareable = ViewDefinition(
            resource="Patient",
            meta={"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
            url="https://example.org/ViewDefinition/shareable",
            name="shareable_patient",
            status="active",
            fhirVersion=["4.0.1"],
            select=[Select(column=[Column(path="id", name="id")])],
        )
        with pytest.raises(ValidationError, match="Column.type"):
            SQLGenerator().generate(shareable)

        tabular = ViewDefinition(
            resource="Patient",
            meta={"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
            status="active",
            select=[Select(column=[Column(path="name", name="name", type="HumanName")])],
        )
        with pytest.raises(ValidationError, match="primitive"):
            SQLGenerator().generate(tabular)

    @pytest.mark.parametrize(
        "kwargs, message",
        [
            ({"name": "_bad", "value": "x", "value_type": "string"}, "sql-name"),
            ({"name": "Good", "value": None, "value_type": "string"}, "no value"),
            ({"name": "BadInteger", "value": "1", "value_type": "integer"}, "valueInteger"),
            ({"name": "BadDateTime", "value": "2024T00:00:00Z", "value_type": "dateTime"}, "valueDateTime"),
            ({"name": "BadInstant", "value": "2024-01T00:00:00Z", "value_type": "instant"}, "valueInstant"),
            ({"name": "BadType", "value": "x", "value_type": "notatype"}, "Unsupported"),
        ],
    )
    def test_direct_view_definition_constants_are_validated(self, kwargs, message):
        """Direct Constant construction validates spec invariants.

        Per SOF-VD-02 SKEPTIC fresh rerun (2026-07-03), the Constant
        dataclass enforces name/value_type/value invariants at construction
        via __post_init__, matching the pattern used by sibling dataclasses
        (Column, ColumnTag, Join). The previous "construct invalid then
        rely on generator" pattern is no longer reachable because the
        constructor now raises first.
        """
        with pytest.raises((ValueError, ValidationError), match=message):
            constant = Constant(**kwargs)
            vd = ViewDefinition(
                resource="Patient",
                constants=[constant],
                select=[Select(column=[Column(path="id", name="id")])],
            )
            SQLGenerator().generate(vd)

    def test_direct_view_definition_duplicate_constants_are_rejected(self):
        """Generator rejects ambiguous duplicate constant names."""
        vd = ViewDefinition(
            resource="Patient",
            constants=[
                Constant(name="Duplicate", value="first", value_type="string"),
                Constant(name="Duplicate", value="second", value_type="string"),
            ],
            select=[Select(column=[Column(path="id = %Duplicate", name="matches")])],
        )

        with pytest.raises(ValidationError, match="Duplicate constant name"):
            SQLGenerator().generate(vd)

    def test_direct_select_iteration_shapes_are_validated(self):
        """Direct dataclass construction cannot bypass select iteration field shapes."""
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(repeat={"path": "name"}, column=[Column(path="$this", name="value")])],
        )

        with pytest.raises(ValidationError, match="repeat"):
            SQLGenerator().generate(vd)

        vd = ViewDefinition(
            resource="Patient",
            select=[Select(repeat="name", column=[Column(path="$this", name="value")])],
        )

        with pytest.raises(ValidationError, match="repeat"):
            SQLGenerator().generate(vd)

        vd = ViewDefinition(
            resource="Patient",
            select=[Select(repeat=[], column=[Column(path="$this", name="value")])],
        )

        with pytest.raises(ValidationError, match="repeat"):
            SQLGenerator().generate(vd)

    @pytest.mark.parametrize(
        "kwargs, message",
        [
            ({"column": {"path": "id", "name": "id"}}, "column"),
            ({"select": None}, "select"),
            ({"select": {"bad": "shape"}}, "select"),
            ({"unionAll": None}, "unionAll"),
            ({"unionAll": {"bad": "shape"}}, "unionAll"),
        ],
    )
    def test_direct_select_containers_are_validated(self, kwargs, message):
        """Direct dataclass construction cannot bypass recursive container shapes."""
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(**kwargs)],
        )

        with pytest.raises(ValidationError, match=message):
            SQLGenerator().generate(vd)

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

    def test_percent_text_inside_string_literal_is_not_undefined_constant(self):
        """FHIRPath string literal content is not a ViewDefinition constant reference."""
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "'%missing'", "name": "literal", "type": "string"}
                ]
            }]
        })

        sql = SQLGenerator().generate(vd)

        assert "%missing" in sql

    def test_duplicate_column_name_across_sibling_and_unionall_branch_rejected(self):
        """unionAll branch columns cannot collide with sibling output columns.

        Per SQL-on-FHIR v2 ValidateColumns, this is a hard parser-level
        "Column Already Defined" error (SOF-VD-03 HISTORIAN fix). The parser
        rejects before SQL generation; the direct-dataclass path is still
        caught by SQLGenerator._validate_unique_output_names.
        """
        # Parser path: parse_view_definition rejects spec-invalid duplicates.
        with pytest.raises(ParseError, match="Duplicate column names"):
            parse_view_definition({
                "resource": "Patient",
                "select": [
                    {"column": [{"path": "id", "name": "dup"}]},
                    {
                        "unionAll": [
                            {"column": [{"path": "gender", "name": "dup"}]},
                            {"column": [{"path": "active", "name": "dup"}]},
                        ]
                    },
                ],
            })

        # Generator direct-dataclass guard remains the safety net for manually
        # constructed ViewDefinitions that bypass the parser.
        vd = ViewDefinition(
            resource="Patient",
            select=[
                Select(column=[Column(path="id", name="dup")]),
                Select(unionAll=[
                    Select(column=[Column(path="gender", name="dup")]),
                    Select(column=[Column(path="active", name="dup")]),
                ]),
            ],
        )
        with pytest.raises(ValidationError, match="Duplicate column names"):
            SQLGenerator().generate(vd)

    def test_unionall_branch_matching_names_are_allowed(self):
        """Matching unionAll branch schemas remain valid when no sibling collides."""
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "id"}]},
                {
                    "unionAll": [
                        {"column": [{"path": "gender", "name": "value"}]},
                        {"column": [{"path": "active", "name": "value"}]},
                    ]
                },
            ],
        })

        sql = SQLGenerator().generate(vd)

        assert "UNION ALL" in sql

    def test_sibling_unionall_output_name_collision_rejected(self):
        """Separate sibling unionAll rowsets cannot project the same output name.

        Per SQL-on-FHIR v2 ValidateColumns, this is a hard parser-level
        "Column Already Defined" error (SOF-VD-03 HISTORIAN fix). The parser
        rejects before SQL generation; the direct-dataclass path is still
        caught by SQLGenerator._validate_unique_output_names.
        """
        # Parser path.
        with pytest.raises(ParseError, match="Duplicate column names"):
            parse_view_definition({
                "resource": "Patient",
                "select": [
                    {
                        "unionAll": [
                            {"column": [{"path": "gender", "name": "value"}]},
                            {"column": [{"path": "active", "name": "value"}]},
                        ]
                    },
                    {
                        "unionAll": [
                            {"column": [{"path": "id", "name": "value"}]},
                            {"column": [{"path": "birthDate", "name": "value"}]},
                        ]
                    },
                ],
            })

        # Direct-dataclass generator guard remains the safety net.
        vd = ViewDefinition(
            resource="Patient",
            select=[
                Select(unionAll=[
                    Select(column=[Column(path="gender", name="value")]),
                    Select(column=[Column(path="active", name="value")]),
                ]),
                Select(unionAll=[
                    Select(column=[Column(path="id", name="value")]),
                    Select(column=[Column(path="birthDate", name="value")]),
                ]),
            ],
        )
        with pytest.raises(ValidationError, match="Duplicate column names"):
            SQLGenerator().generate(vd)

    def test_unionall_branch_type_mismatch_rejected(self):
        """unionAll branches must match column names, order, FHIR types, and collection flags."""
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{
                "unionAll": [
                    {"column": [{"path": "id", "name": "value", "type": "id"}]},
                    {"column": [{"path": "1", "name": "value", "type": "integer"}]},
                ]
            }],
        })

        with pytest.raises(ValidationError, match="column schema"):
            SQLGenerator().generate(vd)

    def test_unionall_branch_collection_mismatch_rejected(self):
        """unionAll branch cardinality is part of the output schema."""
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{
                "unionAll": [
                    {"column": [{"path": "id", "name": "value", "type": "id"}]},
                    {
                        "column": [{
                            "path": "name.given",
                            "name": "value",
                            "type": "id",
                            "collection": True,
                        }]
                    },
                ]
            }],
        })

        with pytest.raises(ValidationError, match="collection flags"):
            SQLGenerator().generate(vd)


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
