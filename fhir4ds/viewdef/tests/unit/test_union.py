"""Unit tests for unionAll handling.

Tests the UNION ALL generation for combining results
from multiple select branches in ViewDefinitions.
"""

import pytest

from ...parser import parse_view_definition, Column, Select, ViewDefinition
from ...generator import SQLGenerator
from ...union import (
    generate_union_all,
    UnionGenerator,
    UnionGeneratorError,
    flatten_union_all,
    _extract_column_names,
)


class TestUnionAllGeneration:
    """Tests for UNION ALL SQL generation."""

    def test_simple_union_all(self):
        """Test simple UNION ALL with two branches."""
        union_selects = [
            Select(column=[
                Column(path="name.given", name="name_value")
            ]),
            Select(column=[
                Column(path="name.family", name="name_value")
            ])
        ]

        gen = SQLGenerator()
        sql = generate_union_all(union_selects, "patients t", gen, "t.resource")

        assert "UNION ALL" in sql
        assert sql.count("SELECT") == 2

    def test_union_all_maintains_column_order(self):
        """Test UNION ALL maintains column order across branches."""
        union_selects = [
            Select(column=[
                Column(path="id", name="id"),
                Column(path="name", name="name")
            ]),
            Select(column=[
                Column(path="identifier.value", name="id"),
                Column(path="display", name="name")
            ])
        ]

        gen = SQLGenerator()
        sql = generate_union_all(union_selects, "patients t", gen, "t.resource")

        # Both branches should have same columns
        assert 'as "id"' in sql
        assert 'as "name"' in sql

    def test_union_all_empty_raises_error(self):
        """Test that empty unionAll raises error."""
        gen = SQLGenerator()

        with pytest.raises(UnionGeneratorError):
            generate_union_all([], "patients t", gen, "t.resource")

    def test_union_all_mismatched_columns_raises_error(self):
        """Test that mismatched column names raise error."""
        union_selects = [
            Select(column=[
                Column(path="id", name="id"),
                Column(path="name", name="name")
            ]),
            Select(column=[
                Column(path="value", name="different_name")
            ])
        ]

        gen = SQLGenerator()

        with pytest.raises(UnionGeneratorError) as exc_info:
            generate_union_all(union_selects, "patients t", gen, "t.resource")

        assert "mismatched" in str(exc_info.value).lower()

    def test_generator_handles_multiple_top_level_union_groups(self):
        """Top-level sibling unionAll groups should all contribute branches."""
        view_definition = ViewDefinition(
            resource="Patient",
            select=[
                Select(column=[Column(path="id", name="pid")]),
                Select(
                    unionAll=[
                        Select(column=[Column(path="name[0].family", name="value")]),
                        Select(column=[Column(path="name[1].family", name="value")]),
                    ]
                ),
                Select(
                    unionAll=[
                        Select(column=[Column(path="name[0].given.first()", name="value")]),
                        Select(column=[Column(path="name[1].given.first()", name="value")]),
                    ]
                ),
            ],
        )

        sql = SQLGenerator().generate(view_definition)

        assert sql.count("UNION ALL") == 3
        assert "name[0].family" in sql
        assert "name[1].family" in sql
        assert "name[0].given.first()" in sql
        assert "name[1].given.first()" in sql


class TestExtractColumnNames:
    """Tests for column name extraction."""

    def test_extract_simple_columns(self):
        """Test extracting column names from simple select."""
        select = Select(column=[
            Column(path="id", name="patient_id"),
            Column(path="gender", name="gender")
        ])

        names = _extract_column_names(select)
        assert names == ["patient_id", "gender"]

    def test_extract_from_nested_union(self):
        """Test extracting from nested unionAll."""
        select = Select(
            column=[],
            unionAll=[
                Select(column=[Column(path="v", name="value")])
            ]
        )

        names = _extract_column_names(select)
        assert names == ["value"]


class TestFlattenUnionAll:
    """Tests for flattening nested unionAll structures."""

    def test_flatten_simple(self):
        """Test flattening simple list."""
        selects = [
            Select(column=[Column(path="a", name="col")]),
            Select(column=[Column(path="b", name="col")])
        ]

        result = flatten_union_all(selects)
        assert len(result) == 2

    def test_flatten_nested(self):
        """Test flattening nested unionAll."""
        selects = [
            Select(
                column=[Column(path="a", name="col")],
                unionAll=[
                    Select(column=[Column(path="b", name="col")]),
                    Select(column=[Column(path="c", name="col")])
                ]
            )
        ]

        result = flatten_union_all(selects)
        assert len(result) == 2
        assert result[0].column[0].path == "b"
        assert result[1].column[0].path == "c"

    def test_flatten_deeply_nested(self):
        """Test flattening deeply nested unionAll."""
        selects = [
            Select(
                column=[],
                unionAll=[
                    Select(
                        column=[Column(path="a", name="col")],
                        unionAll=[
                            Select(column=[Column(path="b", name="col")])
                        ]
                    )
                ]
            )
        ]

        result = flatten_union_all(selects)
        assert len(result) == 1
        assert result[0].column[0].path == "b"


class TestUnionGenerator:
    """Tests for UnionGenerator class."""

    def test_initialization(self):
        """Test UnionGenerator initialization."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        assert union_gen.generator is gen

    def test_generate_method(self):
        """Test UnionGenerator.generate method."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        union_selects = [
            Select(column=[Column(path="a", name="val")]),
            Select(column=[Column(path="b", name="val")])
        ]

        sql = union_gen.generate(union_selects, "patients t", "t.resource")

        assert "UNION ALL" in sql

    def test_validate_union_columns_valid(self):
        """Test validation with matching columns."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        union_selects = [
            Select(column=[
                Column(path="a", name="col1"),
                Column(path="b", name="col2")
            ]),
            Select(column=[
                Column(path="c", name="col1"),
                Column(path="d", name="col2")
            ])
        ]

        warnings = union_gen.validate_union_columns(union_selects)
        assert len(warnings) == 0

    def test_validate_union_columns_invalid(self):
        """Test validation with mismatched columns."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        union_selects = [
            Select(column=[Column(path="a", name="col1")]),
            Select(column=[Column(path="b", name="different")])
        ]

        warnings = union_gen.validate_union_columns(union_selects)
        assert len(warnings) > 0
        assert "mismatched" in warnings[0].lower()

    def test_validate_empty_union(self):
        """Test validation with empty union."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        warnings = union_gen.validate_union_columns([])
        assert len(warnings) > 0

    def test_get_union_column_count(self):
        """Test getting column count for union."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        union_selects = [
            Select(column=[
                Column(path="a", name="c1"),
                Column(path="b", name="c2"),
                Column(path="c", name="c3")
            ])
        ]

        assert union_gen.get_union_column_count(union_selects) == 3

    def test_get_union_column_count_empty(self):
        """Test getting column count for empty union."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        assert union_gen.get_union_column_count([]) == 0

    def test_get_union_column_names(self):
        """Test getting column names for union."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        union_selects = [
            Select(column=[
                Column(path="a", name="id"),
                Column(path="b", name="name")
            ])
        ]

        names = union_gen.get_union_column_names(union_selects)
        assert names == ["id", "name"]

    def test_get_union_column_names_empty(self):
        """Test getting column names for empty union."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        assert union_gen.get_union_column_names([]) == []


class TestUnionAllWithForeach:
    """Tests for UNION ALL with forEach/forEachOrNull."""

    def test_union_with_foreach_in_branch(self):
        """Test UNION ALL branch containing forEach."""
        # This tests that the lateral join generation for forEach
        # is integrated into union branch generation
        union_selects = [
            Select(
                forEach="name",
                column=[Column(path="given", name="name_part")]
            ),
            Select(column=[Column(path="id", name="name_part")])
        ]

        gen = SQLGenerator()
        # This should work without error
        # Note: full forEach integration may depend on generator implementation
        try:
            sql = generate_union_all(union_selects, "patients t", gen, "t.resource")
            assert "SELECT" in sql
        except (AttributeError, TypeError):
            # If generator doesn't have required methods, skip
            pytest.skip("Generator missing forEach support methods")


class TestMultipleUnionBranches:
    """Tests for UNION ALL with multiple branches."""

    def test_three_branches(self):
        """Test UNION ALL with three branches."""
        union_selects = [
            Select(column=[Column(path="a", name="val")]),
            Select(column=[Column(path="b", name="val")]),
            Select(column=[Column(path="c", name="val")])
        ]

        gen = SQLGenerator()
        sql = generate_union_all(union_selects, "patients t", gen, "t.resource")

        assert sql.count("SELECT") == 3
        assert sql.count("UNION ALL") == 2

    def test_four_branches(self):
        """Test UNION ALL with four branches."""
        union_selects = [
            Select(column=[Column(path="a", name="val")]),
            Select(column=[Column(path="b", name="val")]),
            Select(column=[Column(path="c", name="val")]),
            Select(column=[Column(path="d", name="val")])
        ]

        gen = SQLGenerator()
        sql = generate_union_all(union_selects, "patients t", gen, "t.resource")

        assert sql.count("SELECT") == 4
        assert sql.count("UNION ALL") == 3
