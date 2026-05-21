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
from ...generator import SQLGenerator
from ...errors import ValidationError
from ...metadata import (
    SHAREABLE_VIEWDEFINITION_PROFILE,
    TABULAR_VIEWDEFINITION_PROFILE,
    VIEWDEFINITION_RESOURCE_TYPE,
)


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

    def test_column_with_full_fhir_type_uri(self):
        """column.type accepts full FHIR StructureDefinition URIs."""
        vd = parse_view_definition({
            "resource": "Observation",
            "select": [{
                "column": [{
                    "path": "code",
                    "name": "code",
                    "type": "http://hl7.org/fhir/StructureDefinition/CodeableConcept",
                }]
            }],
        })

        assert vd.select[0].column[0].type == ColumnType.CODEABLE_CONCEPT

    @pytest.mark.parametrize("column_type", [1, [], {}, "", None])
    def test_column_type_must_be_uri_string_when_present(self, column_type):
        """column.type is a URI primitive when present."""
        with pytest.raises(ParseError, match="type"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id", "type": column_type}]
                }],
            })

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

    def test_column_with_tags(self):
        """column.tag metadata is parsed and preserved."""
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{
                "column": [{
                    "path": "birthDate",
                    "name": "birth_date",
                    "type": "date",
                    "tag": [
                        {"name": "ansi/type", "value": "DATE"},
                        {"name": "duckdb/type", "value": "DATE"},
                    ],
                }]
            }],
        })

        tags = vd.select[0].column[0].tag
        assert [(tag.name, tag.value) for tag in tags] == [
            ("ansi/type", "DATE"),
            ("duckdb/type", "DATE"),
        ]

    def test_column_with_plural_tags_alias(self):
        """The documented tags example spelling is accepted as an alias."""
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{
                "column": [{
                    "path": "birthDate",
                    "name": "birth_date",
                    "tags": [{"name": "ansi/type", "value": "DATE"}],
                }]
            }],
        })

        assert vd.select[0].column[0].tag[0].name == "ansi/type"

    @pytest.mark.parametrize(
        "tag_value",
        [
            None,
            {"name": "ansi/type", "value": "DATE"},
            [{"name": "ansi/type"}],
            [{"value": "DATE"}],
            [{"name": "", "value": "DATE"}],
            [{"name": "ansi/type", "value": ""}],
            ["bad"],
        ],
    )
    def test_column_tag_must_be_array_with_required_strings(self, tag_value):
        """column.tag is 0..* and each item requires name/value strings."""
        with pytest.raises(ParseError, match="tag"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id", "tag": tag_value}]
                }],
            })

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

    @pytest.mark.parametrize("path", [123, ["id"], {"path": "id"}])
    def test_column_path_must_be_string(self, path):
        """column.path is a required FHIRPath string."""
        with pytest.raises(ParseError, match="path"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": path, "name": "id"}]
                }]
            })

    @pytest.mark.parametrize("name", [123, ["id"], "_bad", "bad-name", "bad.name"])
    def test_column_name_must_be_sql_name(self, name):
        """column.name follows the SQL-on-FHIR sql-name invariant."""
        with pytest.raises(ParseError, match="name|sql-name"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": name}]
                }]
            })

    def test_column_description_must_be_markdown_string(self):
        """column.description is markdown metadata when present."""
        with pytest.raises(ParseError, match="description"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id", "description": 5}]
                }]
            })

    @pytest.mark.parametrize("collection", ["false", "true", 1, None, []])
    def test_column_collection_must_be_boolean(self, collection):
        """column.collection is a boolean logical-model field."""
        with pytest.raises(ParseError, match="collection"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id", "collection": collection}]
                }]
            })

    def test_generator_rejects_direct_column_name_bypass(self):
        """Direct dataclass construction still cannot bypass sql-name."""
        col = Column(path="id", name="_bad")
        with pytest.raises(ValidationError, match="sql-name"):
            SQLGenerator().generate_column_expr(col, "t.resource")


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

    @pytest.mark.parametrize("select_value", ["not-array", {"column": []}, 1])
    def test_view_definition_select_must_be_array(self, select_value):
        """ViewDefinition.select is a required non-empty array."""
        with pytest.raises(ParseError, match="select"):
            parse_view_definition({
                "resource": "Patient",
                "select": select_value,
            })

    @pytest.mark.parametrize("select_item", ["bad", 1, []])
    def test_select_items_must_be_objects(self, select_item):
        """Each ViewDefinition.select item is a BackboneElement object."""
        with pytest.raises(ParseError, match="select"):
            parse_view_definition({
                "resource": "Patient",
                "select": [select_item],
            })

    @pytest.mark.parametrize("column_value", [{"path": "id", "name": "id"}, "bad", 1, None])
    def test_select_column_must_be_array(self, column_value):
        """select.column is an array of column objects."""
        with pytest.raises(ParseError, match="column"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{"column": column_value}],
            })

    @pytest.mark.parametrize("column_item", ["bad", 1, []])
    def test_column_items_must_be_objects(self, column_item):
        """Each select.column item is a BackboneElement object."""
        with pytest.raises(ParseError, match="column"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{"column": [column_item]}],
            })

    @pytest.mark.parametrize("field_name", ["select", "unionAll"])
    def test_nested_repeating_select_fields_must_not_be_null(self, field_name):
        """Present repeating select containers must be arrays, not null."""
        with pytest.raises(ParseError, match=field_name):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id"}],
                    field_name: None,
                }],
            })

    def test_view_definition_from_dict_validates_column_fields(self):
        """The public convenience constructor enforces the same column rules."""
        with pytest.raises(ValueError, match="sql-name"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "_bad"}]
                }]
            })

        with pytest.raises(ValueError, match="description"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id", "description": 5}]
                }]
            })

        with pytest.raises(ValueError, match="column"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "column": None,
                }]
            })

        with pytest.raises(ValueError, match="collection"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id", "collection": "false"}],
                }]
            })

        with pytest.raises(ValueError, match="select"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id"}],
                    "select": None,
                }]
            })

        with pytest.raises(ValueError, match="unionAll"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id"}],
                    "unionAll": None,
                }]
            })

    def test_view_definition_from_dict_reuses_root_parser_validation(self):
        """The public convenience constructor shares parser root rules."""
        with pytest.raises(ValueError, match="sql-name"):
            ViewDefinition.from_dict({
                "name": "_bad",
                "resource": "Patient",
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        with pytest.raises(ValueError, match="resource"):
            ViewDefinition.from_dict({
                "resource": ["Patient"],
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        with pytest.raises(ValueError, match="profile"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "profile": "http://example.org/profile",
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        with pytest.raises(ValueError, match="fhirVersion"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "fhirVersion": ["bogus"],
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        vd = ViewDefinition.from_dict({
            "resource": "Patient",
            "where": {"path": "active = true"},
            "select": [{"column": [{"path": "id", "name": "id"}]}],
        })

        assert vd.where == [{"path": "active = true"}]
        assert "active = true" in SQLGenerator().generate(vd)

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

    @pytest.mark.parametrize("field,value", [
        ("forEach", 1),
        ("forEach", ""),
        ("forEachOrNull", ["telecom"]),
        ("forEachOrNull", ""),
    ])
    def test_select_iteration_fields_must_be_non_empty_strings(self, field, value):
        """forEach and forEachOrNull are optional string FHIRPath expressions."""
        with pytest.raises(ParseError, match=field):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    field: value,
                    "column": [{"path": "$this", "name": "value"}],
                }],
            })

    @pytest.mark.parametrize("repeat", [
        None,
        "name",
        {"path": "name"},
        [1],
        [""],
    ])
    def test_repeat_must_be_string_array(self, repeat):
        """repeat is a repeating string FHIRPath field, not an arbitrary iterable."""
        with pytest.raises(ParseError, match="repeat"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "repeat": repeat,
                    "column": [{"path": "$this", "name": "value"}],
                }],
            })

    @pytest.mark.parametrize("fields", [
        {"forEach": "name", "forEachOrNull": "telecom"},
        {"forEach": "name", "repeat": ["telecom"]},
        {"forEachOrNull": "name", "repeat": ["telecom"]},
    ])
    def test_parse_rejects_mutually_exclusive_iteration_fields(self, fields):
        """sql-expressions allows only one of forEach, forEachOrNull, or repeat."""
        with pytest.raises(ParseError, match="forEach.*forEachOrNull.*repeat"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    **fields,
                    "column": [{"path": "$this", "name": "value"}],
                }],
            })

    def test_view_definition_from_dict_validates_iteration_fields(self):
        """The public convenience constructor enforces select iteration shapes."""
        with pytest.raises(ValueError, match="forEach"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "forEach": 1,
                    "column": [{"path": "$this", "name": "value"}],
                }],
            })

        with pytest.raises(ValueError, match="repeat"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "repeat": {"path": "name"},
                    "column": [{"path": "$this", "name": "value"}],
                }],
            })

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

    def test_select_with_string_where(self):
        """Test parsing select where clause from a convenience string."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ],
                "where": "active = true"
            }]
        }
        ''')

        assert vd.select[0].where == [{"path": "active = true"}]


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

    def test_view_definition_from_dict_uses_singular_constant(self):
        """The public convenience constructor preserves spec-singular constants."""
        vd = ViewDefinition.from_dict({
            "resource": "Patient",
            "constant": [
                {"name": "Female", "valueString": "female"}
            ],
            "select": [{
                "column": [
                    {"path": "gender = %Female", "name": "is_female", "type": "boolean"}
                ]
            }]
        })

        assert len(vd.constants) == 1
        assert vd.constants[0].name == "Female"
        assert vd.constants[0].valueString == "female"

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

    def test_constant_value_canonical(self):
        """Test parsing canonical constant from the spec value[x] choices."""
        vd = parse_view_definition({
            "resource": "Patient",
            "constant": [
                {"name": "ProfileUrl", "valueCanonical": "http://example.org/Profile"}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        })

        assert vd.constants[0].valueCanonical == "http://example.org/Profile"
        assert vd.constants[0].value_type == "canonical"

    def test_constant_value_integer64(self):
        """Test parsing integer64 constant from the spec value[x] choices."""
        vd = parse_view_definition({
            "resource": "Patient",
            "constant": [
                {"name": "LargeIndex", "valueInteger64": "1234567890123"}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        })

        assert vd.constants[0].valueInteger64 == "1234567890123"
        assert vd.constants[0].value_type == "integer64"

    @pytest.mark.parametrize("name", ["_bad", "bad-name", "1bad", "bad.name"])
    def test_constant_name_must_match_sql_name(self, name):
        """constant.name has the same SQL-on-FHIR sql-name invariant as columns."""
        with pytest.raises(ParseError, match="sql-name"):
            parse_view_definition({
                "resource": "Patient",
                "constant": [
                    {"name": name, "valueString": "female"}
                ],
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            })

    def test_constant_must_have_exactly_one_value_choice(self):
        """ViewDefinition.constant.value[x] is a 1..1 choice."""
        with pytest.raises(ParseError, match="exactly one"):
            parse_view_definition({
                "resource": "Patient",
                "constant": [
                    {"name": "Ambiguous", "valueString": "female", "valueInteger": 1}
                ],
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            })

    def test_constant_rejects_unknown_value_choice(self):
        """Unsupported value[x] names fail explicitly instead of falling back."""
        with pytest.raises(ParseError, match="Unsupported"):
            parse_view_definition({
                "resource": "Patient",
                "constant": [
                    {"name": "Unknown", "valueFoo": "bar"}
                ],
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            })

    def test_constant_rejects_null_typed_value(self):
        """A present but null value[x] is not a usable FHIRPath literal."""
        with pytest.raises(ParseError, match="must not be null"):
            parse_view_definition({
                "resource": "Patient",
                "constant": [
                    {"name": "NullString", "valueString": None}
                ],
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            })

    def test_constant_rejects_present_null_repeating_field(self):
        """A present repeating constant field must be an array, not JSON null."""
        with pytest.raises(ParseError, match="constant.*array"):
            parse_view_definition({
                "resource": "Patient",
                "constant": None,
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            })

    @pytest.mark.parametrize("field,value", [
        ("valueCoding", {"system": "http://hl7.org/fhir/gender-identity", "code": "female"}),
        ("valueCodeableConcept", {"coding": [{"system": "http://snomed.info/sct", "code": "73211009"}]}),
    ])
    def test_constant_rejects_non_primitive_value_choices(self, field, value):
        """ViewDefinition.constant.value[x] is limited to the current primitive choices."""
        with pytest.raises(ParseError, match="Unsupported"):
            parse_view_definition({
                "resource": "Patient",
                "constant": [
                    {"name": "Complex", field: value}
                ],
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            })

    @pytest.mark.parametrize("field,value", [
        ("valueBase64Binary", "not base64!"),
        ("valueBoolean", "true"),
        ("valueCode", " bad "),
        ("valueDate", "2024-02-31"),
        ("valueDateTime", "2024-01-01T00:00:00"),
        ("valueDecimal", "1.2"),
        ("valueId", "bad/id"),
        ("valueInstant", "2024-01-01T00:00:00"),
        ("valueInteger", 2147483648),
        ("valueInteger64", 1234567890123),
        ("valueInteger64", "9223372036854775808"),
        ("valueOid", "1.2.3"),
        ("valuePositiveInt", -1),
        ("valueTime", "24:00:00"),
        ("valueUnsignedInt", -1),
        ("valueUri", "not a uri with spaces"),
        ("valueUrl", "not a url with spaces"),
        ("valueUuid", "53fefa32-fcbb-4ff8-8a92-55ee120877b7"),
    ])
    def test_constant_rejects_invalid_primitive_values(self, field, value):
        """FHIR primitive constant values are validated before substitution."""
        with pytest.raises(ParseError, match=field):
            parse_view_definition({
                "resource": "Patient",
                "constant": [
                    {"name": "Invalid", field: value}
                ],
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            })


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

    @pytest.mark.parametrize(
        "join_data, message",
        [
            ({"name": "patient; DROP TABLE x", "resource": "Patient"}, "sql-name"),
            ({"name": "patient", "resource": "DefinitelyNotAResource"}, "ResourceType"),
            ({"name": "patient", "resource": "Patient", "on": {"path": "id"}}, "on"),
        ],
    )
    def test_join_fields_are_validated(self, join_data, message):
        with pytest.raises(ParseError, match=message):
            parse_view_definition({
                "resource": "Observation",
                "select": [{"column": [{"path": "id", "name": "observation_id"}]}],
                "joins": [join_data],
            })


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

    def test_view_definition_with_string_where(self):
        """Test parsing top-level where from a convenience string."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "where": "active = true",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }]
        }
        ''')

        assert vd.where == [{"path": "active = true"}]

    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises ParseError."""
        with pytest.raises(ParseError):
            parse_view_definition('not valid json')

    def test_non_object_raises_error(self):
        """Test that non-object JSON raises ParseError."""
        with pytest.raises(ParseError):
            parse_view_definition('["array", "not", "object"]')

    def test_resource_must_be_single_resource_type_code(self):
        """SQL-on-FHIR ViewDefinition.resource is a single ResourceType code."""
        with pytest.raises(ParseError, match="resource.*string"):
            parse_view_definition({
                "resource": ["Patient", "Observation"],
                "select": [{
                    "column": [{"path": "id", "name": "id"}]
                }]
            })

    def test_unknown_resource_type_raises_error(self):
        """The required ResourceType binding rejects unknown FHIR resource codes."""
        with pytest.raises(ParseError, match="ResourceType"):
            parse_view_definition({
                "resource": "NotARealFHIRResource",
                "select": [{
                    "column": [{"path": "id", "name": "id"}]
                }]
            })

    @pytest.mark.parametrize("name", ["Good_1", "A1"])
    def test_view_definition_name_accepts_sql_name(self, name):
        """ViewDefinition.name uses the SQL-on-FHIR sql-name invariant."""
        vd = parse_view_definition({
            "name": name,
            "resource": "Patient",
            "select": [{
                "column": [{"path": "id", "name": "id"}]
            }]
        })

        assert vd.name == name

    @pytest.mark.parametrize("name", ["_bad", "bad-name", "bad.name", "1bad", "", 123])
    def test_view_definition_name_must_be_sql_name_when_present(self, name):
        """ViewDefinition.name follows the same sql-name invariant as columns."""
        with pytest.raises(ParseError, match="sql-name|non-empty"):
            parse_view_definition({
                "name": name,
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id"}]
                }]
            })

    def test_profile_and_fhir_version_are_preserved(self):
        """Root profile/fhirVersion declarations are part of the logical model."""
        vd = parse_view_definition({
            "resourceType": VIEWDEFINITION_RESOURCE_TYPE,
            "id": "PatientView",
            "url": "https://example.org/ViewDefinition/patient-view",
            "version": "1.0.0",
            "status": "draft",
            "resource": "Patient",
            "profile": [
                "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"
            ],
            "fhirVersion": ["4.0.1", "5.0.0"],
            "select": [{
                "column": [{"path": "id", "name": "id"}]
            }]
        })

        assert vd.profile == [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"
        ]
        assert vd.fhirVersion == ["4.0.1", "5.0.0"]
        assert vd.resourceType == VIEWDEFINITION_RESOURCE_TYPE
        assert vd.id == "PatientView"
        assert vd.url == "https://example.org/ViewDefinition/patient-view"
        assert vd.version == "1.0.0"
        assert vd.status == "draft"

        round_tripped = parse_view_definition(vd.to_dict())
        assert round_tripped.to_dict() == vd.to_dict()

    def test_view_definition_to_dict_uses_official_json_field_names(self):
        """Serializer emits singular SQL-on-FHIR fields accepted by the parser."""
        vd = parse_view_definition({
            "resource": "Patient",
            "constant": [{"name": "Gender", "valueCode": "female"}],
            "select": [{
                "column": [{
                    "path": "gender",
                    "name": "gender",
                    "type": "code",
                    "tag": [{"name": "database-type", "value": "VARCHAR"}],
                }]
            }]
        })

        serialized = vd.to_dict()

        assert "constant" in serialized
        assert "constants" not in serialized
        assert "tag" in serialized["select"][0]["column"][0]
        assert "tags" not in serialized["select"][0]["column"][0]
        assert parse_view_definition(serialized).to_dict() == serialized

    def test_shareable_profile_enforces_required_metadata_and_column_types(self):
        """ShareableViewDefinition activates profile-specific cardinality rules."""
        with pytest.raises(ParseError, match="ShareableViewDefinition.*url"):
            parse_view_definition({
                "meta": {"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
                "resource": "Patient",
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        with pytest.raises(ParseError, match="Column.type"):
            parse_view_definition({
                "meta": {"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
                "url": "https://example.org/ViewDefinition/shareable",
                "name": "shareable_patient",
                "fhirVersion": ["4.0.1"],
                "resource": "Patient",
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        vd = parse_view_definition({
            "meta": {"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
            "url": "https://example.org/ViewDefinition/shareable",
            "name": "shareable_patient",
            "fhirVersion": ["4.0.1"],
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id", "type": "id"}]}],
        })
        assert vd.has_profile(SHAREABLE_VIEWDEFINITION_PROFILE)

    def test_tabular_profile_rejects_collections_and_complex_column_types(self):
        """TabularViewDefinition only permits scalar primitive columns."""
        with pytest.raises(ParseError, match="collection"):
            parse_view_definition({
                "meta": {"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
                "resource": "Patient",
                "select": [{
                    "column": [{
                        "path": "name.given",
                        "name": "given",
                        "type": "string",
                        "collection": True,
                    }]
                }],
            })

        with pytest.raises(ParseError, match="primitive"):
            parse_view_definition({
                "meta": {"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "name", "name": "name", "type": "HumanName"}]
                }],
            })

    def test_xml_view_definition_parse_error_is_explicit(self):
        """XML input is not silently treated as malformed JSON."""
        with pytest.raises(ParseError, match="XML ViewDefinition parsing is not supported"):
            parse_view_definition("<ViewDefinition><resource value='Patient'/></ViewDefinition>")

    def test_profile_must_be_canonical_string_array(self):
        """profile is 0..* canonical(StructureDefinition), represented as strings."""
        with pytest.raises(ParseError, match="profile"):
            parse_view_definition({
                "resource": "Patient",
                "profile": "http://hl7.org/fhir/StructureDefinition/Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id"}]
                }]
            })

    def test_fhir_version_must_use_fhir_version_binding(self):
        """fhirVersion values come from the required FHIRVersion binding."""
        with pytest.raises(ParseError, match="FHIRVersion"):
            parse_view_definition({
                "resource": "Patient",
                "fhirVersion": ["definitely-not-a-fhir-version"],
                "select": [{
                    "column": [{"path": "id", "name": "id"}]
                }]
            })

    def test_optional_string_arrays_reject_present_null(self):
        """Present profile/fhirVersion fields must be arrays, not JSON null."""
        for field_name in ("profile", "fhirVersion"):
            with pytest.raises(ParseError, match=f"{field_name}.*array"):
                parse_view_definition({
                    "resource": "Patient",
                    field_name: None,
                    "select": [{
                        "column": [{"path": "id", "name": "id"}]
                    }]
                })


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
        """Permissive validation warns for forEach and forEachOrNull together."""
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
        assert any(
            "forEach" in warning and "forEachOrNull" in warning
            for warning in warnings
        )

    @pytest.mark.parametrize("select", [
        Select(forEach="name", repeat=["telecom"], column=[Column(path="id", name="id")]),
        Select(forEachOrNull="name", repeat=["telecom"], column=[Column(path="id", name="id")]),
    ])
    def test_validate_warns_for_repeat_with_foreach_variants(self, select):
        """Permissive validation warns for the full sql-expressions constraint."""
        vd = ViewDefinition(resource="Patient", select=[select])

        warnings = validate_view_definition(vd)
        assert any("forEach" in warning and "repeat" in warning for warning in warnings)


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
