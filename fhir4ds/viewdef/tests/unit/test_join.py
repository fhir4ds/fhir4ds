"""Unit tests for JOIN generation.

Tests the generation of SQL JOIN clauses from ViewDefinition
join specifications for linking FHIR resources.
"""


import pytest

from ...parser import Join, parse_view_definition
from ...types import JoinType
from ...join import (
    resource_to_table_name,
    generate_on_condition,
    generate_join,
    JoinGenerator,
    VALID_JOIN_TYPES,
)


class TestResourceToTableName:
    """Tests for resource to table name conversion."""

    def test_simple_resource(self):
        """Test simple resource name to table name."""
        assert resource_to_table_name("Patient") == "patients"
        assert resource_to_table_name("Observation") == "observations"
        assert resource_to_table_name("Condition") == "conditions"

    def test_resource_lowercase(self):
        """Test resource name is lowercased."""
        assert resource_to_table_name("PATIENT") == "patients"
        assert resource_to_table_name("Patient") == "patients"


class TestValidJoinTypes:
    """Tests for valid join types."""

    def test_valid_types(self):
        """Test that expected types are valid."""
        assert "inner" in VALID_JOIN_TYPES
        assert "left" in VALID_JOIN_TYPES
        assert "right" in VALID_JOIN_TYPES
        assert "full" in VALID_JOIN_TYPES


class TestGenerateOnCondition:
    """Tests for ON condition generation."""

    def test_on_condition_with_pair(self):
        """Test ON condition with path pair."""
        on_clauses = [
            {"path": "subject.reference"},
            {"path": "'Patient/' + id"}
        ]

        result = generate_on_condition(on_clauses, "t", "patient")

        assert "fhirpath_text" in result
        assert "subject.reference" in result
        assert "''Patient/'' + id" in result
        assert "=" in result

    def test_on_condition_single_path(self):
        """Test ON condition with single path."""
        on_clauses = [
            {"path": "subject.reference"}
        ]

        result = generate_on_condition(on_clauses, "t", "patient")

        assert "fhirpath_text" in result
        assert "subject.reference" in result

    def test_on_condition_empty(self):
        """Test ON condition with empty list raises ValueError."""
        with pytest.raises(ValueError, match="JOIN requires at least one ON clause"):
            generate_on_condition([], "t", "patient")


class TestGenerateJoin:
    """Tests for JOIN clause generation."""

    def test_inner_join(self):
        """Test generating INNER JOIN."""
        join = Join(
            name="patient",
            resource="Patient",
            on=[
                {"path": "subject.reference"},
                {"path": "'Patient/' + id"}
            ],
            type="inner"
        )

        result = generate_join(join, "t")

        assert "JOIN" in result
        assert "patients patient" in result
        assert "ON" in result

    def test_left_join(self):
        """Test generating LEFT JOIN."""
        join = Join(
            name="patient",
            resource="Patient",
            on=[{"path": "subject.reference"}, {"path": "id"}],
            type="left"
        )

        result = generate_join(join, "t")

        assert "LEFT JOIN" in result

    def test_right_join(self):
        """Test generating RIGHT JOIN."""
        join = Join(
            name="encounter",
            resource="Encounter",
            on=[{"path": "encounter.reference"}, {"path": "id"}],
            type="right"
        )

        result = generate_join(join, "t")

        assert "RIGHT JOIN" in result

    def test_full_join(self):
        """Test generating FULL JOIN."""
        join = Join(
            name="practitioner",
            resource="Practitioner",
            on=[{"path": "performer.reference"}, {"path": "id"}],
            type="full"
        )

        result = generate_join(join, "t")

        assert "FULL JOIN" in result

    def test_invalid_join_type_raises_error(self):
        """Test that an invalid join type raises ValueError instead of silently defaulting."""
        with pytest.raises(ValueError, match="Unknown join type"):
            Join(
                name="test",
                resource="Test",
                on=[{"path": "id"}],
                type="invalid"
            )

    def test_join_structure(self):
        """Test the structure of generated JOIN."""
        join = Join(
            name="patient",
            resource="Patient",
            on=[
                {"path": "subject.reference"},
                {"path": "'Patient/' + id"}
            ],
            type="inner"
        )

        result = generate_join(join, "t")

        # Should have proper indentation/structure
        assert "JOIN patients patient ON" in result
        assert "fhirpath_text(t.resource" in result
        assert "fhirpath_text(patient.resource" in result


class TestJoinGenerator:
    """Tests for JoinGenerator class."""

    def test_initialization(self):
        """Test JoinGenerator initialization."""
        gen = JoinGenerator()

        assert gen.base_alias == "t"
        assert len(gen.joins) == 0
        assert "t" in gen.aliases

    def test_initialization_custom_alias(self):
        """Test initialization with custom base alias."""
        gen = JoinGenerator("base")

        assert gen.base_alias == "base"
        assert "base" in gen.aliases

    def test_add_join(self):
        """Test adding a join."""
        gen = JoinGenerator()
        join = Join(
            name="patient",
            resource="Patient",
            on=[{"path": "subject.reference"}, {"path": "id"}],
            type="inner"
        )

        result = gen.add_join(join)

        assert "JOIN" in result
        assert len(gen.joins) == 1
        assert "patient" in gen.aliases

    def test_add_multiple_joins(self):
        """Test adding multiple joins."""
        gen = JoinGenerator()

        gen.add_join(Join(name="patient", resource="Patient", on=[{"path": "subject.reference"}, {"path": "id"}], type="inner"))
        gen.add_join(Join(name="encounter", resource="Encounter", on=[{"path": "encounter.reference"}, {"path": "id"}], type="left"))

        assert len(gen.joins) == 2
        assert "patient" in gen.aliases
        assert "encounter" in gen.aliases

    def test_duplicate_alias_raises_error(self):
        """Test that duplicate alias raises ValueError."""
        gen = JoinGenerator()

        gen.add_join(Join(name="patient", resource="Patient", on=[{"path": "subject.reference"}, {"path": "id"}], type="inner"))

        with pytest.raises(ValueError) as exc_info:
            gen.add_join(Join(name="patient", resource="Person", on=[{"path": "link.reference"}, {"path": "id"}], type="inner"))

        assert "conflicts" in str(exc_info.value).lower()

    def test_add_joins(self):
        """Test adding multiple joins at once."""
        gen = JoinGenerator()
        joins = [
            Join(name="patient", resource="Patient", on=[{"path": "subject.reference"}, {"path": "id"}], type="inner"),
            Join(name="encounter", resource="Encounter", on=[{"path": "encounter.reference"}, {"path": "id"}], type="left")
        ]

        results = gen.add_joins(joins)

        assert len(results) == 2
        assert len(gen.joins) == 2

    def test_generate_all(self):
        """Test generating all joins as string."""
        gen = JoinGenerator()

        gen.add_join(Join(name="patient", resource="Patient", on=[{"path": "subject.reference"}, {"path": "id"}], type="inner"))
        gen.add_join(Join(name="encounter", resource="Encounter", on=[{"path": "encounter.reference"}, {"path": "id"}], type="left"))

        result = gen.generate_all()

        assert "JOIN patients patient" in result
        assert "LEFT JOIN encounters encounter" in result

    def test_generate_all_empty(self):
        """Test generating all when no joins."""
        gen = JoinGenerator()

        result = gen.generate_all()

        assert result == ""

    def test_clear(self):
        """Test clearing all joins."""
        gen = JoinGenerator()

        gen.add_join(Join(name="patient", resource="Patient", on=[{"path": "subject.reference"}, {"path": "id"}], type="inner"))
        gen.clear()

        assert len(gen.joins) == 0
        assert "t" in gen.aliases  # Base alias remains
        assert "patient" not in gen.aliases

    def test_has_joins(self):
        """Test has_joins method."""
        gen = JoinGenerator()

        assert not gen.has_joins()

        gen.add_join(Join(name="patient", resource="Patient", on=[{"path": "subject.reference"}, {"path": "id"}], type="inner"))

        assert gen.has_joins()


class TestJoinParsing:
    """Tests for join parsing in ViewDefinitions."""

    def test_parse_single_join(self):
        """Test parsing ViewDefinition with single join."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{
                "column": [{"path": "id", "name": "observation_id"}]
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

        assert len(vd.joins) == 1
        assert vd.joins[0].name == "patient"
        assert vd.joins[0].resource == "Patient"
        assert len(vd.joins[0].on) == 2

    def test_parse_multiple_joins(self):
        """Test parsing ViewDefinition with multiple joins."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{
                "column": [{"path": "id", "name": "observation_id"}]
            }],
            "joins": [
                {"name": "patient", "resource": "Patient", "on": []},
                {"name": "encounter", "resource": "Encounter", "on": []}
            ]
        }
        ''')

        assert len(vd.joins) == 2

    def test_parse_join_with_type(self):
        """Test parsing join with explicit type."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{
                "column": [{"path": "id", "name": "id"}]
            }],
            "joins": [
                {"name": "patient", "resource": "Patient", "type": "left", "on": []}
            ]
        }
        ''')

        assert vd.joins[0].type == JoinType.LEFT

    def test_parse_join_default_type(self):
        """Test join defaults to inner type."""
        vd = parse_view_definition('''
        {
            "resource": "Observation",
            "select": [{
                "column": [{"path": "id", "name": "id"}]
            }],
            "joins": [
                {"name": "patient", "resource": "Patient", "on": []}
            ]
        }
        ''')

        assert vd.joins[0].type == JoinType.INNER


class TestComplexJoins:
    """Tests for complex join scenarios."""

    def test_join_with_complex_on_conditions(self):
        """Test join with complex ON conditions."""
        join = Join(
            name="patient",
            resource="Patient",
            on=[
                {"path": "subject.where(system='http://hl7.org/fhir/resource-types').reference"},
                {"path": "'Patient/' + id"}
            ],
            type="inner"
        )

        result = generate_join(join, "t")

        assert "subject.where" in result
        assert "fhirpath_text" in result

    def test_cascade_joins(self):
        """Test cascade of multiple joins."""
        gen = JoinGenerator()

        # First join references base table
        gen.add_join(Join(
            name="patient",
            resource="Patient",
            on=[{"path": "subject.reference"}, {"path": "'Patient/' + id"}],
            type="inner"
        ))

        # Second join could reference first join (in real usage)
        gen.add_join(Join(
            name="organization",
            resource="Organization",
            on=[{"path": "managingOrganization.reference"}, {"path": "'Organization/' + id"}],
            type="left"
        ))

        assert len(gen.joins) == 2
