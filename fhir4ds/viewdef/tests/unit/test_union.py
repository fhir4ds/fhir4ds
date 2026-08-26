"""Unit tests for unionAll handling.

Tests the UNION ALL generation for combining results
from multiple select branches in ViewDefinitions.
"""

import json

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath

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
        assert 'FROM "patients" t' in sql

    def test_union_all_rejects_injected_base_query(self):
        """Legacy helper treats base_query as table plus alias, not raw SQL."""
        union_selects = [
            Select(column=[Column(path="id", name="id")])
        ]
        gen = SQLGenerator()

        con = duckdb.connect()
        try:
            con.execute("CREATE TABLE sentinel (id INTEGER)")
            con.execute("INSERT INTO sentinel VALUES (1)")

            with pytest.raises(UnionGeneratorError):
                generate_union_all(
                    union_selects,
                    "patients t; DROP TABLE sentinel; --",
                    gen,
                    "t.resource",
                )

            assert con.execute("SELECT COUNT(*) FROM sentinel").fetchone()[0] == 1
        finally:
            con.close()

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

    def test_generator_cross_joins_multiple_top_level_union_groups(self):
        """Top-level sibling unionAll groups behave like select rowsets."""
        view_definition = ViewDefinition(
            resource="Patient",
            select=[
                Select(column=[Column(path="id", name="pid")]),
                Select(
                    unionAll=[
                        Select(column=[Column(path="name[0].family", name="family_value")]),
                        Select(column=[Column(path="name[1].family", name="family_value")]),
                    ]
                ),
                Select(
                    unionAll=[
                        Select(column=[Column(path="name[0].given.first()", name="given_value")]),
                        Select(column=[Column(path="name[1].given.first()", name="given_value")]),
                    ]
                ),
            ],
        )

        sql = SQLGenerator().generate(view_definition)

        assert sql.count("UNION ALL") == 3
        assert 'as "family_value"' in sql
        assert 'as "given_value"' in sql
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

    def test_validate_union_columns_type_mismatch_invalid(self):
        """Validation checks names, order, declared FHIR types, and cardinality."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        union_selects = [
            Select(column=[Column(path="id", name="value", type="id")]),
            Select(column=[Column(path="active", name="value", type="boolean")]),
        ]

        warnings = union_gen.validate_union_columns(union_selects)

        assert len(warnings) > 0
        assert "mismatched column schema" in warnings[0].lower()
        assert "boolean" in warnings[0]

    def test_validate_union_columns_collection_mismatch_invalid(self):
        """Collection cardinality is part of the unionAll branch schema."""
        gen = SQLGenerator()
        union_gen = UnionGenerator(gen)

        union_selects = [
            Select(column=[Column(path="name.family", name="value", type="string", collection=True)]),
            Select(column=[Column(path="id", name="value", type="string", collection=False)]),
        ]

        warnings = union_gen.validate_union_columns(union_selects)

        assert len(warnings) > 0
        assert "mismatched column schema" in warnings[0].lower()
        assert "True" in warnings[0]
        assert "False" in warnings[0]

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
        union_selects = [
            Select(
                forEach="name",
                column=[Column(path="given.first()", name="name_part", type="string")]
            ),
            Select(column=[Column(path="id", name="name_part", type="string")])
        ]

        gen = SQLGenerator()
        sql = generate_union_all(union_selects, "patients t", gen, "t.resource")
        assert "JOIN LATERAL" in sql

        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        register_fhirpath(con)
        try:
            patient = {
                "resourceType": "Patient",
                "id": "p1",
                "name": [
                    {"given": ["A"]},
                    {"given": ["B"]},
                ],
            }
            con.execute("CREATE TABLE patients (resource JSON)")
            con.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

            assert con.execute(sql).fetchall() == [("A",), ("B",), ("p1",)]
        finally:
            con.close()

    def test_union_branch_with_nested_union_preserves_direct_columns(self):
        """Legacy helper preserves direct columns plus nested unionAll columns."""
        union_selects = [
            Select(
                column=[Column(path="'outer-a'", name="outer", type="string")],
                select=[
                    Select(
                        unionAll=[
                            Select(column=[Column(path="'inner-1'", name="inner", type="string")]),
                            Select(column=[Column(path="'inner-2'", name="inner", type="string")]),
                        ]
                    )
                ],
            ),
            Select(
                column=[Column(path="'outer-b'", name="outer", type="string")],
                select=[
                    Select(
                        unionAll=[
                            Select(column=[Column(path="'inner-3'", name="inner", type="string")]),
                            Select(column=[Column(path="'inner-4'", name="inner", type="string")]),
                        ]
                    )
                ],
            ),
        ]

        sql = generate_union_all(union_selects, "patients t", SQLGenerator(), "t.resource")
        assert 'as "outer"' in sql
        assert 'as "inner"' in sql

        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        register_fhirpath(con)
        try:
            con.execute("CREATE TABLE patients (resource JSON)")
            con.execute(
                "INSERT INTO patients VALUES (?)",
                [json.dumps({"resourceType": "Patient", "id": "p1"})],
            )

            assert con.execute(sql).fetchall() == [
                ("outer-a", "inner-1"),
                ("outer-a", "inner-2"),
                ("outer-b", "inner-3"),
                ("outer-b", "inner-4"),
            ]
        finally:
            con.close()


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


class TestUnionAllForEachOrNullSuppression:
    """Regression tests for null-row suppression across UNION ALL branches.

    Per SQL-on-FHIR v2 Process(S, N) step 3, a forEachOrNull select with
    empty foci emits exactly one null row *for that selection structure*.
    Only wrapper copies replicated by unionAll expansion may be suppressed
    in non-first branches; independent sibling selects keep their own null
    row even when they repeat the same forEachOrNull path.
    """

    def _run(self, view, resources):
        con = duckdb.connect()
        try:
            register_fhirpath(con)
            gen = SQLGenerator(strict_collection=True)
            vd = parse_view_definition(json.dumps(view))
            sql = gen.generate(vd)
            con.execute("CREATE TABLE resources (resource JSON)")
            for r in resources:
                con.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])
            import re
            sql = re.sub(r"FROM (\w+) t", "FROM resources t", sql)
            sql = sql.replace(
                "WHERE t.resourceType =", "WHERE t.resource->>'$.resourceType' ="
            )
            res = con.execute(sql)
            cols = [d[0] for d in res.description]
            return [dict(zip(cols, row)) for row in res.fetchall()]
        finally:
            con.close()

    def test_sibling_foreachornull_null_row_not_suppressed(self):
        """QA-001: a sibling select repeating the wrapper's forEachOrNull
        path must keep its null row in every union alternative."""
        view = {
            "resource": "Patient",
            "select": [
                {"unionAll": [
                    {"column": [{"path": "id", "name": "v"}]},
                    {"column": [{"path": "gender", "name": "v"}]},
                ]},
                {"forEachOrNull": "telecom",
                 "column": [{"path": "%context.value", "name": "tv"}]},
            ],
        }
        patient = {"resourceType": "Patient", "id": "p2", "gender": "female"}
        rows = self._run(view, [patient])
        assert sorted(r["v"] for r in rows) == ["female", "p2"]
        assert all(r["tv"] is None for r in rows)

    def test_wrapper_foreachornull_union_with_sibling_same_path(self):
        """QA-001: wrapper forEachOrNull+unionAll still emits exactly one
        all-null row, cross-joined with the sibling's own null row."""
        view = {
            "resource": "Patient",
            "select": [
                {"forEachOrNull": "telecom",
                 "unionAll": [
                     {"column": [{"path": "%context.value", "name": "v"}]},
                     {"column": [{"path": "%context.system", "name": "v"}]},
                 ]},
                {"forEachOrNull": "telecom",
                 "column": [{"path": "%context.value", "name": "tv"}]},
            ],
        }
        patient = {"resourceType": "Patient", "id": "p2", "gender": "female"}
        rows = self._run(view, [patient])
        assert rows == [{"v": None, "tv": None}]

    def test_wrapper_foreachornull_union_alone_single_null_row(self):
        """Pre-existing pin: wrapper forEachOrNull + unionAll with no
        sibling emits exactly one all-null row (no per-branch duplicates)."""
        view = {
            "resource": "Patient",
            "select": [{
                "forEachOrNull": "telecom",
                "unionAll": [
                    {"column": [{"path": "%context.value", "name": "v"},
                                {"path": "%context.system", "name": "s"}]},
                    {"column": [{"path": "%context.value", "name": "v"},
                                {"path": "%context.system", "name": "s"}]},
                ],
            }],
        }
        patient = {"resourceType": "Patient", "id": "p2", "gender": "female"}
        rows = self._run(view, [patient])
        assert rows == [{"v": None, "s": None}]

    def test_nested_wrapper_foreachornull_union_single_null_row(self):
        """QA-001 (HISTORIAN): a forEachOrNull+unionAll wrapper nested under
        a forEach select must also emit exactly one null row per focus
        across its union branches — suppression bookkeeping must cover
        wrappers at ANY nesting depth, not just the top-level select list."""
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "contact",
                "select": [
                    {"column": [{"path": "name.family", "name": "f"}]},
                    {"forEachOrNull": "telecom",
                     "unionAll": [
                         {"column": [{"path": "value", "name": "v"}]},
                         {"column": [{"path": "system", "name": "v"}]},
                     ]},
                ],
            }],
        }
        patient = {
            "resourceType": "Patient", "id": "p1",
            "contact": [
                {"name": {"family": "A"}},
                {"name": {"family": "B"}},
            ],
        }
        rows = self._run(view, [patient])
        assert sorted((r["f"], r["v"]) for r in rows) == [("A", None), ("B", None)]

    def test_nested_wrapper_foreachornull_union_under_foreachornull(self):
        """QA-001 (HISTORIAN): nested wrapper under an outer forEachOrNull
        that is also empty — exactly one all-null row, no per-branch copies."""
        view = {
            "resource": "Patient",
            "select": [{
                "forEachOrNull": "contact",
                "select": [
                    {"column": [{"path": "name.family", "name": "f"}]},
                    {"forEachOrNull": "telecom",
                     "unionAll": [
                         {"column": [{"path": "value", "name": "v"}]},
                         {"column": [{"path": "system", "name": "v"}]},
                     ]},
                ],
            }],
        }
        patient = {"resourceType": "Patient", "id": "p3"}
        rows = self._run(view, [patient])
        assert rows == [{"f": None, "v": None}]

    def test_wrapper_foreachornull_union_inside_union_branch(self):
        """QA-001 (HISTORIAN): forEachOrNull+unionAll wrappers nested inside
        unionAll branches emit one null row per wrapper instance (2 wrappers
        -> 2 rows), not one per branch copy (4 rows)."""
        branch = {
            "select": [{
                "forEachOrNull": "telecom",
                "unionAll": [
                    {"column": [{"path": "value", "name": "v"}]},
                    {"column": [{"path": "system", "name": "v"}]},
                ],
            }],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "unionAll": [
                    {"column": [{"path": "id", "name": "a"}], **branch},
                    {"column": [{"path": "gender", "name": "a"}], **branch},
                ],
            }],
        }
        patient = {"resourceType": "Patient", "id": "p5", "gender": "male"}
        rows = self._run(view, [patient])
        assert sorted(r["a"] for r in rows) == ["male", "p5"]
        assert all(r["v"] is None for r in rows)

    def test_nested_wrapper_foreachornull_union_populated_foci(self):
        """Pin: with non-empty foci the nested wrapper cross joins per-focus
        rows with each union branch (no suppression applied)."""
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "contact",
                "select": [
                    {"column": [{"path": "name.family", "name": "f"}]},
                    {"forEachOrNull": "telecom",
                     "unionAll": [
                         {"column": [{"path": "value", "name": "v"}]},
                         {"column": [{"path": "system", "name": "v"}]},
                     ]},
                ],
            }],
        }
        patient = {
            "resourceType": "Patient", "id": "p6",
            "contact": [{"name": {"family": "Jones"},
                         "telecom": [{"value": "555", "system": "phone"}]}],
        }
        rows = self._run(view, [patient])
        assert sorted(r["v"] for r in rows) == ["555", "phone"]
        assert all(r["f"] == "Jones" for r in rows)
