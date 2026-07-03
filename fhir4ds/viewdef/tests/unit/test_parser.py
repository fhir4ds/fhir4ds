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
from ...types import ColumnTag, ColumnType, JoinType
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

    def test_column_with_plural_tags_alias_rejected(self):
        """Official column metadata field is singular tag, not plural tags."""
        with pytest.raises(ParseError, match="Unsupported field 'tags'"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{
                        "path": "birthDate",
                        "name": "birth_date",
                        "tags": [{"name": "ansi/type", "value": "DATE"}],
                    }]
                }],
            })

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

    @pytest.mark.parametrize("description", [5, None])
    def test_column_description_must_be_markdown_string(self, description):
        """column.description is markdown metadata when present."""
        with pytest.raises(ParseError, match="description"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id", "description": description}]
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
        """Direct dataclass construction rejects sql-name violations.

        SOF-VD-03 SKEPTIC fix (2026-07-03): Column.__post_init__ now enforces
        the sql-name invariant at construction time, matching the
        Constant.__post_init__ pattern. The generator boundary is still
        protected, but invalid Columns cannot be constructed in the first
        place.
        """
        with pytest.raises(ValueError, match="sql-name"):
            Column(path="id", name="_bad")


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

    def test_unionall_must_not_be_empty_when_present(self):
        """Present select.unionAll must contain at least one branch."""
        with pytest.raises(ParseError, match="unionAll"):
            parse_view_definition({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id"}],
                    "unionAll": [],
                }],
            })

        with pytest.raises(ValueError, match="unionAll"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id"}],
                    "unionAll": [],
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

        for description in (5, None):
            with pytest.raises(ValueError, match="description"):
                ViewDefinition.from_dict({
                    "resource": "Patient",
                    "select": [{
                        "column": [{"path": "id", "name": "id", "description": description}]
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

    def test_from_dict_preserves_typed_parse_error_per_spec_sof_vd01_historian(self):
        """SOF-VD-01 HISTORIAN QA-001: ViewDefinition.from_dict is a public
        convenience wrapper around parse_view_definition and must preserve
        typed exception information. GLOBAL_RULES.md "No Silent Fallbacks:
        Fail fast with typed exceptions." SQLOnFHIRError subclasses ValueError,
        so callers can still catch either form."""
        # An invalid ResourceType code raises ParseError from the parser.
        # from_dict must propagate the typed ParseError, not wrap it as a
        # generic ValueError that erases the exception type.
        with pytest.raises(ParseError, match="ResourceType"):
            ViewDefinition.from_dict({
                "resource": "FooBar",
                "status": "active",
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        # Typed ParseError must also be catchable as ValueError (because
        # SQLOnFHIRError inherits from ValueError) for backward compatibility
        # with existing callers.
        with pytest.raises(ValueError, match="ResourceType"):
            ViewDefinition.from_dict({
                "resource": "FooBar",
                "status": "active",
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        # Non-dict input still raises ValueError directly (pre-existing behavior).
        with pytest.raises(ValueError, match="expects a dictionary"):
            ViewDefinition.from_dict("not a dict")

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
        ("forEach", None),
        ("forEachOrNull", ["telecom"]),
        ("forEachOrNull", ""),
        ("forEachOrNull", None),
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
        [],
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

        with pytest.raises(ValueError, match="repeat"):
            ViewDefinition.from_dict({
                "resource": "Patient",
                "select": [{
                    "repeat": [],
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
            "constant": [
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

    def test_plural_constants_alias_is_rejected(self):
        """The SQL-on-FHIR JSON field is singular `constant`."""
        with pytest.raises(ParseError, match="constants.*singular 'constant'"):
            parse_view_definition({
                "resource": "Patient",
                "constants": [
                    {"name": "Female", "valueString": "female"}
                ],
                "select": [{
                    "column": [
                        {"path": "id", "name": "patient_id"}
                    ]
                }]
            })

    def test_constant_value_code(self):
        """Test parsing constant with code value."""
        vd = parse_view_definition('''
        {
            "resource": "Patient",
            "constant": [
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
            "constant": [
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
            "constant": [
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

    def test_constant_rejects_duplicate_names(self):
        """A ViewDefinition constant name must resolve to one value."""
        with pytest.raises(ParseError, match="Duplicate constant name"):
            parse_view_definition({
                "resource": "Patient",
                "constant": [
                    {"name": "Duplicate", "valueString": "first"},
                    {"name": "Duplicate", "valueString": "second"},
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
        ("valueDateTime", "2024T00:00:00Z"),
        ("valueDateTime", "2024-01T00:00:00Z"),
        ("valueDateTime", "2024-01-01T00:00:00"),
        ("valueDecimal", "1.2"),
        ("valueId", "bad/id"),
        ("valueInstant", "2024T00:00:00Z"),
        ("valueInstant", "2024-01T00:00:00Z"),
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

    @pytest.mark.parametrize(
        "field_name",
        [
            "resourceType",
            "id",
            "meta",
            "url",
            "version",
            "status",
            "title",
            "description",
        ],
    )
    def test_root_metadata_must_not_be_present_null(self, field_name):
        """Strict JSON parsing rejects present null root metadata fields."""
        data = {
            "resource": "Patient",
            field_name: None,
            "select": [{
                "column": [{"path": "id", "name": "id"}]
            }],
        }

        with pytest.raises(ParseError, match=field_name):
            parse_view_definition(data)

        with pytest.raises(ValueError, match=field_name):
            ViewDefinition.from_dict(data)

    def test_direct_dataclass_none_root_metadata_still_means_omitted(self):
        """Direct dataclass None remains the public API representation of absence."""
        vd = ViewDefinition(
            resource="Patient",
            resourceType=None,
            id=None,
            meta=None,
            url=None,
            version=None,
            status=None,
            title=None,
            description=None,
            select=[Select(column=[Column(path="id", name="id")])],
        )

        serialized = vd.to_dict()

        assert serialized == {
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id"}]}],
        }

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

    @pytest.mark.parametrize(
        "kwargs, message",
        [
            ({"resource": ["Patient"]}, "ResourceType|string"),
            ({"resource": "DefinitelyNotAResource"}, "ResourceType"),
            ({"profile": None}, "profile"),
            ({"meta": {"profile": "http://example.org/Profile"}}, "meta.profile"),
            ({"fhirVersion": "4.0.1"}, "fhirVersion.*array"),
            ({"fhirVersion": ["9.9.9"]}, "FHIRVersion"),
        ],
    )
    def test_view_definition_to_dict_validates_root_logical_model_fields(self, kwargs, message):
        """Serializer enforces root logical-model shape for direct dataclass input."""
        base = {"resource": "Patient"}
        base.update(kwargs)
        vd = ViewDefinition(
            **base,
            select=[Select(column=[Column(path="id", name="id")])],
        )

        with pytest.raises(ValueError, match=message):
            vd.to_dict()

    @pytest.mark.parametrize(
        "select_value, message",
        [
            ([], "non-empty"),
            (None, "select"),
            ({"column": []}, "select"),
            ([{"column": []}], "Select objects"),
        ],
    )
    def test_view_definition_to_dict_validates_select_shape(self, select_value, message):
        """Serializer enforces ViewDefinition.select cardinality and item shape."""
        vd = ViewDefinition(resource="Patient", select=select_value)

        with pytest.raises(ValueError, match=message):
            vd.to_dict()

    @pytest.mark.parametrize(
        "kwargs, message",
        [
            ({"path": "", "name": "id"}, "path"),
            ({"path": "id", "name": "_bad"}, "sql-name"),
            ({"path": "id", "name": "id", "description": 5}, "description"),
            ({"path": "id", "name": "id", "collection": "false"}, "collection"),
        ],
    )
    def test_view_definition_to_dict_validates_column_fields(self, kwargs, message):
        """Direct Column construction rejects spec violations.

        SOF-VD-03 SKEPTIC fix (2026-07-03): Column.__post_init__ now enforces
        path/name/description/collection invariants at construction time
        using the canonical validate_column_fields/validate_optional_boolean
        helpers, matching the Constant.__post_init__ pattern added by
        SOF-VD-02 SKEPTIC. Previously, direct construction deferred these
        checks to to_dict()/SQLGenerator._validate_column_shape.
        """
        with pytest.raises(ValueError, match=message):
            Column(**kwargs)

    def test_view_definition_to_dict_retains_valid_root_where_description(self):
        """Root where metadata is preserved after serializer validation."""
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(column=[Column(path="id", name="id")])],
            where=[{"path": "active", "description": "Only active patients"}],
        )

        assert vd.to_dict()["where"] == [
            {"path": "active", "description": "Only active patients"}
        ]

    @pytest.mark.parametrize(
        "where, message",
        [
            (None, "ViewDefinition.where"),
            ([{"description": "missing path"}], "path"),
            ([{"path": None}], "path"),
            ([{"path": "active", "description": None}], "description"),
            ([{"path": "active", "description": 5}], "description"),
        ],
    )
    def test_view_definition_to_dict_validates_root_where_fields(self, where, message):
        """Serializer does not emit invalid direct root where objects."""
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(column=[Column(path="id", name="id")])],
            where=where,
        )

        with pytest.raises(ValueError, match=message):
            vd.to_dict()

    @pytest.mark.parametrize(
        "select, message",
        [
            (Select(column={"path": "id", "name": "id"}), "column"),
            (Select(column=[{"path": "id", "name": "id"}]), "Column objects"),
            (Select(select=None), "select"),
            (Select(select=[{"column": []}]), "Select objects"),
            (Select(unionAll=None), "unionAll"),
            (Select(unionAll=[{"column": []}]), "Select objects"),
            (Select(forEach=1), "forEach"),
            (Select(repeat="name"), "repeat"),
            (Select(repeat=[]), "repeat"),
            (Select(forEach="name", forEachOrNull="telecom"), "forEach"),
            (
                Select(
                    column=[Column(path="id", name="id")],
                    select=[Select(where=[{"notPath": "active"}])],
                ),
                "path",
            ),
            (
                Select(
                    column=[Column(path="id", name="id")],
                    select=[Select(where=[{"path": "active", "description": None}])],
                ),
                "description",
            ),
            (
                Select(
                    column=[Column(path="id", name="id")],
                    select=[Select(where=[{"path": "active", "description": 5}])],
                ),
                "description",
            ),
        ],
    )
    def test_view_definition_to_dict_validates_nested_select_fields(self, select, message):
        """Serializer validates direct Select container and iterator fields."""
        vd = ViewDefinition(resource="Patient", select=[select])

        with pytest.raises(ValueError, match=message):
            vd.to_dict()

    def test_shareable_profile_enforces_required_metadata_and_column_types(self):
        """ShareableViewDefinition activates profile-specific cardinality rules."""
        with pytest.raises(ParseError, match="ShareableViewDefinition.*url"):
            parse_view_definition({
                "meta": {"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
                "status": "active",
                "resource": "Patient",
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        with pytest.raises(ParseError, match="ShareableViewDefinition.*status"):
            parse_view_definition({
                "meta": {"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
                "url": "https://example.org/ViewDefinition/shareable",
                "name": "shareable_patient",
                "fhirVersion": ["4.0.1"],
                "resource": "Patient",
                "select": [{"column": [{"path": "id", "name": "id", "type": "id"}]}],
            })

        with pytest.raises(ParseError, match="Column.type"):
            parse_view_definition({
                "meta": {"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
                "url": "https://example.org/ViewDefinition/shareable",
                "name": "shareable_patient",
                "status": "active",
                "fhirVersion": ["4.0.1"],
                "resource": "Patient",
                "select": [{"column": [{"path": "id", "name": "id"}]}],
            })

        vd = parse_view_definition({
            "meta": {"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
            "url": "https://example.org/ViewDefinition/shareable",
            "name": "shareable_patient",
            "status": "active",
            "fhirVersion": ["4.0.1"],
            "resource": "Patient",
            "select": [{"column": [{"path": "id", "name": "id", "type": "id"}]}],
        })
        assert vd.has_profile(SHAREABLE_VIEWDEFINITION_PROFILE)

    def test_tabular_profile_rejects_collections_and_complex_column_types(self):
        """TabularViewDefinition only permits scalar primitive columns."""
        with pytest.raises(ParseError, match="TabularViewDefinition.*status"):
            parse_view_definition({
                "meta": {"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "id", "name": "id", "type": "id"}]
                }],
            })

        with pytest.raises(ParseError, match="collection"):
            parse_view_definition({
                "meta": {"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
                "status": "active",
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
                "status": "active",
                "resource": "Patient",
                "select": [{
                    "column": [{"path": "name", "name": "name", "type": "HumanName"}]
                }],
            })

    def test_to_dict_validates_supported_profile_constraints(self):
        """Direct serializers must not emit invalid profiled official JSON."""
        shareable = ViewDefinition(
            resource="Patient",
            meta={"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
            status="active",
            select=[Select(column=[Column(path="id", name="id")])],
        )
        with pytest.raises(ValueError, match="ShareableViewDefinition.*url"):
            shareable.to_dict()

        missing_status = ViewDefinition(
            resource="Patient",
            meta={"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
            url="https://example.org/ViewDefinition/shareable",
            name="shareable_patient",
            fhirVersion=["4.0.1"],
            select=[Select(column=[Column(path="id", name="id", type="id")])],
        )
        with pytest.raises(ValueError, match="ShareableViewDefinition.*status"):
            missing_status.to_dict()

        tabular_missing_status = ViewDefinition(
            resource="Patient",
            meta={"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
            select=[Select(column=[Column(path="id", name="id", type="id")])],
        )
        with pytest.raises(ValueError, match="TabularViewDefinition.*status"):
            tabular_missing_status.to_dict()

        tabular = ViewDefinition(
            resource="Patient",
            meta={"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
            status="active",
            select=[Select(column=[Column(path="name", name="name", type="HumanName")])],
        )
        with pytest.raises(ValueError, match="TabularViewDefinition.*primitive"):
            tabular.to_dict()

    def test_column_tag_to_dict_revalidates_direct_tag_objects(self):
        """Direct serializer boundaries recheck required tag name/value fields."""
        tag = ColumnTag("ansi/type", "DATE")
        tag.name = None
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(column=[Column(path="id", name="id", tag=[tag])])],
        )

        with pytest.raises(ValueError, match="Column.tag.name"):
            vd.to_dict()

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

        with pytest.raises(ParseError, match="canonical"):
            parse_view_definition({
                "resource": "Patient",
                "profile": ["not a canonical with spaces"],
                "select": [{
                    "column": [{"path": "id", "name": "id"}]
                }]
            })

    def test_profile_accepts_version_suffixed_canonical(self):
        """profile canonical declarations may carry a FHIR canonical version suffix."""
        profile = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient|7.0.0"
        vd = parse_view_definition({
            "resource": "Patient",
            "profile": [profile],
            "select": [{
                "column": [{"path": "id", "name": "id"}]
            }]
        })

        assert vd.profile == [profile]

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

    @pytest.mark.parametrize(
        "vd, fragments",
        [
            (
                ViewDefinition(
                    resource="DefinitelyNotAResource",
                    select=[Select(column=[Column(path="id", name="id")])],
                ),
                ("ViewDefinition.resource", "ResourceType"),
            ),
            (
                ViewDefinition(
                    resource="Patient",
                    fhirVersion=["9.9.9"],
                    select=[Select(column=[Column(path="id", name="id")])],
                ),
                ("ViewDefinition.fhirVersion", "FHIRVersion"),
            ),
            (
                ViewDefinition(
                    resource="Patient",
                    name="_bad",
                    select=[Select(column=[Column(path="id", name="id")])],
                ),
                ("ViewDefinition.name", "sql-name"),
            ),
            (
                # SOF-VD-03 SKEPTIC fresh rerun (2026-07-03): the Column
                # dataclass now enforces path/name/description/collection
                # invariants in __post_init__, so we mutate a valid Column
                # to exercise the permissive warning path that still
                # surfaces sql-name violations for dataclasses constructed
                # before validation tightened.
                ViewDefinition(
                    resource="Patient",
                    select=[
                        Select(
                            column=[
                                (lambda c: (setattr(c, "name", "_bad"), c)[1])(
                                    Column(path="id", name="placeholder")
                                )
                            ]
                        )
                    ],
                ),
                ("Column.name", "sql-name"),
            ),
            (
                # SOF-VD-02 SKEPTIC fresh rerun (2026-07-03): the Constant
                # dataclass enforces name/value invariants in __post_init__,
                # so we mutate a valid Constant to exercise the permissive
                # warning path that still surfaces sql-name violations for
                # dataclasses constructed before validation tightened.
                ViewDefinition(
                    resource="Patient",
                    constants=[
                        (lambda c: (setattr(c, "name", "_bad"), c)[1])(
                            Constant(name="Placeholder", value="x", value_type="string")
                        )
                    ],
                    select=[Select(column=[Column(path="id", name="id")])],
                ),
                ("Constant.name", "sql-name"),
            ),
        ],
    )
    def test_validate_warns_for_sof_vd10_binding_and_sql_name_constraints(self, vd, fragments):
        """Permissive validation reports SOF-VD-10 constraints instead of raising."""
        warning_text = "\n".join(validate_view_definition(vd))

        for fragment in fragments:
            assert fragment in warning_text

    @pytest.mark.parametrize(
        "vd, fragments",
        [
            (
                ViewDefinition(
                    resource="Patient",
                    meta={"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
                    status="active",
                    select=[Select(column=[Column(path="id", name="id")])],
                ),
                ("ShareableViewDefinition", "ViewDefinition.url"),
            ),
            (
                ViewDefinition(
                    resource="Patient",
                    meta={"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
                    url="https://example.org/ViewDefinition/shareable",
                    name="shareable_patient",
                    fhirVersion=["4.0.1"],
                    select=[Select(column=[Column(path="id", name="id", type="id")])],
                ),
                ("ShareableViewDefinition", "ViewDefinition.status"),
            ),
            (
                ViewDefinition(
                    resource="Patient",
                    meta={"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
                    select=[Select(column=[Column(path="id", name="id", type="id")])],
                ),
                ("TabularViewDefinition", "ViewDefinition.status"),
            ),
            (
                ViewDefinition(
                    resource="Patient",
                    meta={"profile": [TABULAR_VIEWDEFINITION_PROFILE]},
                    status="active",
                    select=[Select(column=[Column(path="name", name="name", type="HumanName")])],
                ),
                ("TabularViewDefinition", "primitive"),
            ),
        ],
    )
    def test_validate_warns_for_sof_vd12_supported_profile_constraints(self, vd, fragments):
        """Permissive validation reports supported Shareable/Tabular constraints."""
        warning_text = "\n".join(validate_view_definition(vd))

        for fragment in fragments:
            assert fragment in warning_text


class TestDuplicateColumnNameRejectionPerSpecSofVd03Historian:
    """SQL-on-FHIR v2 ValidateColumns algorithm step 2.1: a duplicate column
    name in the effective output schema is a hard "Column Already Defined"
    error. The parser and ViewDefinition.to_dict() must reject spec-invalid
    duplicates at the logical-model boundary, not defer to SQL generation.

    Backing fix: SOF-VD-03 HISTORIAN iter 1 (2026-07-03).
    """

    BASE = {
        "resource": "Patient",
    }

    def _expect_dup_rejected(self, select_list):
        with pytest.raises(ParseError, match="Duplicate column names"):
            parse_view_definition({**self.BASE, "select": select_list})

    def test_duplicate_within_single_select_rejected_at_parser(self):
        self._expect_dup_rejected([{
            "column": [
                {"path": "id", "name": "dup"},
                {"path": "active", "name": "dup"},
            ]
        }])

    def test_duplicate_across_sibling_selects_rejected_at_parser(self):
        self._expect_dup_rejected([
            {"column": [{"path": "id", "name": "id"}]},
            {"forEach": "address",
             "column": [{"path": "postalCode", "name": "id"}]},
        ])

    def test_duplicate_in_nested_select_rejected_at_parser(self):
        self._expect_dup_rejected([{
            "column": [{"path": "id", "name": "x"}],
            "select": [{"forEach": "address",
                        "column": [{"path": "postalCode", "name": "x"}]}],
        }])

    def test_duplicate_between_parent_and_unionall_branch_rejected_at_parser(self):
        self._expect_dup_rejected([
            {"column": [{"path": "id", "name": "dup"}]},
            {"unionAll": [
                {"column": [{"path": "gender", "name": "dup"}]},
                {"column": [{"path": "active", "name": "dup"}]},
            ]},
        ])

    def test_duplicate_between_two_sibling_unionall_rowsets_rejected_at_parser(self):
        self._expect_dup_rejected([
            {"unionAll": [
                {"column": [{"path": "gender", "name": "value"}]},
                {"column": [{"path": "active", "name": "value"}]},
            ]},
            {"unionAll": [
                {"column": [{"path": "id", "name": "value"}]},
                {"column": [{"path": "birthDate", "name": "value"}]},
            ]},
        ])

    def test_matching_unionall_branch_names_within_one_rowset_are_allowed(self):
        """unionAll branch schemas must match by name -- not a duplicate."""
        vd = parse_view_definition({**self.BASE, "select": [{
            "unionAll": [
                {"column": [{"path": "gender", "name": "value"}]},
                {"column": [{"path": "active", "name": "value"}]},
            ]
        }]})
        assert len(vd.select[0].unionAll) == 2

    def test_distinct_names_within_and_across_selects_are_allowed(self):
        vd = parse_view_definition({**self.BASE, "select": [
            {"column": [{"path": "id", "name": "id"},
                        {"path": "active", "name": "active"}]},
            {"forEach": "address",
             "column": [{"path": "postalCode", "name": "zip"}]},
        ]})
        assert len(vd.select) == 2

    def test_to_dict_rejects_direct_dataclass_duplicate_columns(self):
        """Serializer boundary stays aligned with parser."""
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(column=[
                Column(path="id", name="dup"),
                Column(path="active", name="dup"),
            ])],
        )
        with pytest.raises(ValueError, match="Duplicate column names"):
            vd.to_dict()

    def test_to_dict_allows_matching_unionall_branch_names(self):
        """Serializer must not flag matching unionAll branch schemas."""
        vd = ViewDefinition(
            resource="Patient",
            select=[Select(unionAll=[
                Select(column=[Column(path="gender", name="value")]),
                Select(column=[Column(path="active", name="value")]),
            ])],
        )
        data = vd.to_dict()
        assert "unionAll" in data["select"][0]


class TestWhitespaceFhirPathRejectionPerSpecSofVd03Explorer:
    """SQL-on-FHIR v2 ViewDefinition: required FHIRPath string fields
    (``column.path``, ``select.forEach``, ``select.forEachOrNull``,
    ``where.path``) are 1..1 / 0..1 FHIRPath expressions. FHIRPath 3 lexical
    grammar requires at least one expression token; whitespace-only strings
    are not valid FHIRPath expressions and must be rejected at the
    logical-model boundary, not deferred to SQL generation.

    Backing fix: SOF-VD-03 EXPLORER iter 1 (2026-07-03).
    """

    BASE = {"resource": "Patient"}

    @pytest.mark.parametrize("whitespace", ["   ", "\t", "\n", "\t \n", "\r"])
    def test_parser_rejects_whitespace_column_path(self, whitespace: str):
        """column.path 1..1 FHIRPath -- whitespace-only is rejected."""
        with pytest.raises(ParseError, match="path"):
            parse_view_definition({
                **self.BASE,
                "select": [{"column": [{"path": whitespace, "name": "id"}]}],
            })

    @pytest.mark.parametrize("whitespace", ["   ", "\t", "\n"])
    def test_parser_rejects_whitespace_for_each(self, whitespace: str):
        """select.forEach 0..1 FHIRPath -- whitespace-only is rejected."""
        with pytest.raises(ParseError, match="forEach"):
            parse_view_definition({
                **self.BASE,
                "select": [{
                    "forEach": whitespace,
                    "column": [{"path": "id", "name": "id"}],
                }],
            })

    @pytest.mark.parametrize("whitespace", ["   ", "\t", "\n"])
    def test_parser_rejects_whitespace_for_each_or_null(self, whitespace: str):
        """select.forEachOrNull 0..1 FHIRPath -- whitespace-only is rejected."""
        with pytest.raises(ParseError, match="forEachOrNull"):
            parse_view_definition({
                **self.BASE,
                "select": [{
                    "forEachOrNull": whitespace,
                    "column": [{"path": "id", "name": "id"}],
                }],
            })

    @pytest.mark.parametrize("whitespace", ["   ", "\t", "\n"])
    def test_parser_rejects_whitespace_where_path(self, whitespace: str):
        """where.path 1..1 FHIRPath -- whitespace-only is rejected at root."""
        with pytest.raises(ParseError, match="path"):
            parse_view_definition({
                **self.BASE,
                "select": [{"column": [{"path": "id", "name": "id"}]}],
                "where": [{"path": whitespace}],
            })

    @pytest.mark.parametrize("whitespace", ["   ", "\t", "\n"])
    def test_parser_rejects_whitespace_where_path_in_select(self, whitespace: str):
        """where.path 1..1 FHIRPath -- whitespace-only is rejected in nested select."""
        with pytest.raises(ParseError, match="path"):
            parse_view_definition({
                **self.BASE,
                "select": [{
                    "column": [{"path": "id", "name": "id"}],
                    "where": [{"path": whitespace}],
                }],
            })

    @pytest.mark.parametrize("whitespace", ["   ", "\t", "\n"])
    def test_direct_column_construction_rejects_whitespace_path(self, whitespace: str):
        """Direct Column dataclass construction also rejects whitespace path."""
        with pytest.raises(ValueError, match="path"):
            Column(path=whitespace, name="id")

    def test_parser_still_accepts_path_with_internal_whitespace(self):
        """Paths with non-whitespace content surrounded by whitespace are fine.

        FHIRPath grammar allows whitespace between tokens; only truly
        whitespace-only strings are invalid.
        """
        vd = parse_view_definition({
            **self.BASE,
            "select": [{
                "column": [{"path": "  id  ", "name": "id"}],
            }],
        })
        # The validated value preserves the original non-empty string.
        assert vd.select[0].column[0].path == "  id  "

    def test_parser_still_accepts_complex_fhirpath_with_whitespace_tokens(self):
        """Complex FHIRPath expressions with internal whitespace are still valid."""
        vd = parse_view_definition({
            **self.BASE,
            "select": [{
                "column": [{
                    "path": "name.where(use = 'official').given",
                    "name": "given_name",
                }],
            }],
        })
        assert vd.select[0].column[0].path == "name.where(use = 'official').given"


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
