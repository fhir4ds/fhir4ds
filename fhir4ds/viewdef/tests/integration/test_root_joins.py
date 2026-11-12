"""Root-join SQL emission (fhir4ds extension, OMOP S0).

The ``joins`` field parses and validates but was never EMITTED by
SQLGenerator before S0 (JoinGenerator existed in join.py, unit-tested in
isolation, wired nowhere; the integration test in test_duckdb.py
documented the gap in its own comment). These tests pin the bounded S0
surface: root-level joins with equality-of-scalar-projection ON pairs,
LEFT/INNER keywords, source_table staging mode, join-prefixed column
paths, and the extension's guard rails (odd ON clause, alias conflicts,
iteration-context rejection).
"""

import json

import pytest

import fhir4ds
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator
from fhir4ds.viewdef.errors import ValidationError


def _make_conn():
    con = fhir4ds.create_connection()
    con.execute("CREATE TABLE __vd_src (resource JSON)")
    return con


OBSERVATION = {
    "resourceType": "Observation",
    "id": "o1",
    "status": "final",
    "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]},
    "subject": {"reference": "Patient/p1"},
    "effectiveDateTime": "2024-03-01",
    "valueQuantity": {"value": 120, "unit": "mmHg"},
}

OBSERVATION_UNMAPPED = {
    "resourceType": "Observation",
    "id": "o2",
    "status": "final",
    "code": {"coding": [{"system": "http://loinc.org", "code": "unknown-code"}]},
    "subject": {"reference": "Patient/p1"},
    "effectiveDateTime": "2024-03-02",
    "valueQuantity": {"value": 80, "unit": "mmHg"},
}

CONCEPTMAP = {
    "resourceType": "ConceptMap",
    "id": "loinc-to-omop",
    "status": "active",
    "group": [
        {
            "source": "http://loinc.org",
            "element": [
                {"code": "8480-6", "target": [{"code": "3038553", "equivalence": "equal"}]},
            ],
        }
    ],
}

PATIENT = {
    "resourceType": "Patient",
    "id": "p1",
    "gender": "male",
}


JOIN_VD = {
    "resource": "Observation",
    "select": [
        {
            "column": [
                {"name": "obs_id", "path": "id"},
                {"name": "loinc", "path": "code.coding.where(system='http://loinc.org').code.first()"},
                {"name": "concept_id", "path": "cm.group.element.target.code.first()"},
            ],
        }
    ],
    "joins": [
        {
            "name": "cm",
            "resource": "ConceptMap",
            "on": [
                {"path": "code.coding.where(system='http://loinc.org').code.first()"},
                {"path": "cm.group.element.code"},
            ],
            "type": "left",
        }
    ],
}


class TestRootJoinEmission:
    def test_left_join_emits_and_executes(self):
        con = _make_conn()
        for r in (OBSERVATION, OBSERVATION_UNMAPPED, CONCEPTMAP, PATIENT):
            con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        vd = parse_view_definition(JOIN_VD)
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        assert 'LEFT JOIN' in sql
        rows = con.execute(sql).fetchall()
        by_id = {r[0]: r for r in rows}
        assert by_id["o1"][2] == "3038553"  # resolved through the join
        assert by_id["o2"][2] is None  # left join keeps unmapped rows

    def test_inner_join_drops_unmatched(self):
        con = _make_conn()
        for r in (OBSERVATION, OBSERVATION_UNMAPPED, CONCEPTMAP, PATIENT):
            con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        vd = parse_view_definition({**JOIN_VD, "joins": [{**JOIN_VD["joins"][0], "type": "inner"}]})
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        assert "\nJOIN " in sql or "JOIN (SELECT" in sql
        rows = con.execute(sql).fetchall()
        assert [r[0] for r in rows] == ["o1"]

    def test_default_mode_uses_pluralized_tables(self):
        vd = parse_view_definition(JOIN_VD)
        sql = SQLGenerator().generate(vd)
        assert "conceptmaps" in sql
        assert "__vd_src" not in sql

    def test_on_clause_pair_forms_equality(self):
        vd = parse_view_definition(JOIN_VD)
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        assert "fhirpath_text(t.resource" in sql
        assert 'fhirpath_text("cm".resource' in sql

    def test_where_can_reference_join(self):
        con = _make_conn()
        for r in (OBSERVATION, CONCEPTMAP, PATIENT):
            con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
        vd = parse_view_definition({
            **JOIN_VD,
            "where": [{"path": "cm.group.element.target.code.first() = '3038553'"}],
        })
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        rows = con.execute(sql).fetchall()
        assert [r[0] for r in rows] == ["o1"]


class TestRootJoinGuards:
    def test_odd_on_clause_rejected(self):
        vd = parse_view_definition({
            **JOIN_VD,
            "joins": [{**JOIN_VD["joins"][0], "on": [{"path": "id"}]}],
        })
        with pytest.raises(ValidationError, match="equality pairs"):
            SQLGenerator(source_table="__vd_src").generate(vd)

    def test_duplicate_join_name_rejected(self):
        vd = parse_view_definition({
            **JOIN_VD,
            "joins": [JOIN_VD["joins"][0], JOIN_VD["joins"][0]],
        })
        with pytest.raises(ValidationError, match="Duplicate join name"):
            SQLGenerator(source_table="__vd_src").generate(vd)

    def test_base_alias_conflict_rejected(self):
        vd = parse_view_definition({
            **JOIN_VD,
            "joins": [{**JOIN_VD["joins"][0], "name": "t"}],
        })
        with pytest.raises(ValidationError, match="base table alias"):
            SQLGenerator(source_table="__vd_src").generate(vd)

    def test_join_path_inside_iteration_rejected(self):
        vd = parse_view_definition({
            **JOIN_VD,
            "select": [{
                "forEach": "code.coding",
                "column": [{"name": "x", "path": "cm.group.element.code"}],
            }],
        })
        with pytest.raises(ValidationError, match="iteration context"):
            SQLGenerator(source_table="__vd_src").generate(vd)


class TestRootJoinDefaultModeExecution:
    def test_pluralized_tables_execute(self):
        con = fhir4ds.create_connection()
        con.execute("CREATE TABLE observations (resource JSON)")
        con.execute("CREATE TABLE conceptmaps (resource JSON)")
        con.execute("INSERT INTO observations VALUES (?)", [json.dumps(OBSERVATION)])
        con.execute("INSERT INTO conceptmaps VALUES (?)", [json.dumps(CONCEPTMAP)])
        vd = parse_view_definition(JOIN_VD)
        sql = SQLGenerator().generate(vd)
        rows = con.execute(sql).fetchall()
        assert rows == [("o1", "8480-6", "3038553")]


class TestRootJoinRightAndFullPreserveUnmatchedRows:
    """V23-002-D5: right/full joins over a shared source_table.

    The shared-table resourceType restriction defines the base RELATION, not a
    row filter. Emitting it as a WHERE predicate drops exactly the
    join-preserved rows that carry a NULL base resource (their `t.resource` is
    NULL, so the predicate is false), which silently degrades RIGHT and FULL
    joins to inner joins. The restriction belongs on the FROM side.
    """

    RIGHT_FULL_VD = {
        "resource": "Patient",
        "joins": [
            {
                "name": "pr",
                "resource": "Practitioner",
                "type": "right",
                "on": [{"path": "id"}, {"path": "pr.id"}],
            }
        ],
        "select": [
            {
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "pr.id", "name": "prid"},
                ]
            }
        ],
    }

    def _load(self, con):
        for r in (
            {"resourceType": "Patient", "id": "p1"},
            {"resourceType": "Patient", "id": "p2"},
            {"resourceType": "Practitioner", "id": "p1"},
            {"resourceType": "Practitioner", "id": "p9"},  # no matching patient
        ):
            con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])

    def test_right_join_keeps_unmatched_joined_rows(self):
        con = _make_conn()
        self._load(con)
        vd = parse_view_definition(self.RIGHT_FULL_VD)
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        assert "RIGHT JOIN" in sql
        # The base relation is restricted in FROM, not by a WHERE row filter.
        assert "SELECT * FROM \"__vd_src\"" in sql
        assert "json_extract_string(t.resource, '$.resourceType')" not in sql
        rows = sorted(str(r) for r in con.execute(sql).fetchall())
        assert rows == ["('p1', 'p1')", "(None, 'p9')"]

    def test_full_join_keeps_rows_from_both_sides(self):
        con = _make_conn()
        self._load(con)
        vd = parse_view_definition(
            {**self.RIGHT_FULL_VD,
             "joins": [{**self.RIGHT_FULL_VD["joins"][0], "type": "full"}]}
        )
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        assert "FULL JOIN" in sql
        rows = sorted(str(r) for r in con.execute(sql).fetchall())
        assert rows == [
            "('p1', 'p1')",
            "('p2', None)",
            "(None, 'p9')",
        ]

    def test_inner_and_left_keep_the_where_filter(self):
        """Only right/full move the restriction into FROM."""
        con = _make_conn()
        self._load(con)
        for jtype, expected in (("inner", 1), ("left", 2)):
            vd = parse_view_definition(
                {**self.RIGHT_FULL_VD,
                 "joins": [{**self.RIGHT_FULL_VD["joins"][0], "type": jtype}]}
            )
            sql = SQLGenerator(source_table="__vd_src").generate(vd)
            assert "SELECT * FROM \"__vd_src\"" not in sql
            assert "json_extract_string(t.resource, '$.resourceType') = 'Patient'" in sql
            assert len(con.execute(sql).fetchall()) == expected

    def test_filter_does_not_leak_across_generate_calls(self):
        """A reused generator must not carry the FROM-restriction decision."""
        con = _make_conn()
        self._load(con)
        gen = SQLGenerator(source_table="__vd_src")
        gen.generate(parse_view_definition(
            {**self.RIGHT_FULL_VD,
             "joins": [{**self.RIGHT_FULL_VD["joins"][0], "type": "right"}]}
        ))
        plain = {k: v for k, v in self.RIGHT_FULL_VD.items() if k != "joins"}
        sql = gen.generate(parse_view_definition(plain))
        assert "json_extract_string(t.resource, '$.resourceType') = 'Patient'" in sql
        assert len(con.execute(sql).fetchall()) == 2


class TestJoinPrefixedPathInSelectWhere:
    """V23-003-D5: select-level `where` must route join-prefixed paths.

    Root `where` routes `<alias>.` paths to the joined table's resource, but
    select-level `where` resolved them against the BASE resource, where the
    alias does not exist. The predicate then quietly evaluated to empty and
    dropped every row — a silent wrong rowset with no error.
    """

    VD = {
        "resource": "Patient",
        "joins": [
            {
                "name": "jp",
                "resource": "Practitioner",
                "type": "right",
                "on": [{"path": "id"}, {"path": "jp.id"}],
            }
        ],
        "select": [
            {
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "jp.id", "name": "jid"},
                ]
            }
        ],
    }

    def _load(self, con):
        for r in (
            {"resourceType": "Patient", "id": "p1"},
            {"resourceType": "Practitioner", "id": "x1"},
        ):
            con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])

    def test_select_where_routes_to_joined_table(self):
        con = _make_conn()
        self._load(con)
        vd = parse_view_definition(
            {
                **self.VD,
                "select": [
                    {**self.VD["select"][0], "where": [{"path": "jp.id.exists()"}]}
                ],
            }
        )
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        assert 'fhirpath_json("jp".resource' in sql
        assert "fhirpath_json(t.resource, 'jp.id" not in sql
        assert con.execute(sql).fetchall() == [(None, "x1")]

    def test_select_where_matches_root_where_rowset(self):
        con = _make_conn()
        self._load(con)
        root = parse_view_definition(
            {**self.VD, "where": [{"path": "jp.id.exists()"}]}
        )
        sel = parse_view_definition(
            {
                **self.VD,
                "select": [
                    {**self.VD["select"][0], "where": [{"path": "jp.id.exists()"}]}
                ],
            }
        )
        gen = SQLGenerator(source_table="__vd_src")
        assert (
            sorted(con.execute(gen.generate(root)).fetchall())
            == sorted(con.execute(gen.generate(sel)).fetchall())
        )

    def test_select_where_without_join_prefix_unchanged(self):
        con = _make_conn()
        self._load(con)
        vd = parse_view_definition(
            {
                **self.VD,
                "joins": [{**self.VD["joins"][0], "type": "left"}],
                "select": [
                    {
                        **self.VD["select"][0],
                        "where": [{"path": "id = 'p1'"}],
                    }
                ],
            }
        )
        sql = SQLGenerator(source_table="__vd_src").generate(vd)
        assert "fhirpath_json(t.resource" in sql
        assert con.execute(sql).fetchall() == [("p1", None)]

    def test_join_prefixed_select_where_inside_iteration_rejected(self):
        vd = parse_view_definition(
            {
                **self.VD,
                "select": [
                    {
                        "forEach": "name",
                        "column": [{"path": "family", "name": "fam"}],
                        "where": [{"path": "jp.id.exists()"}],
                    }
                ],
            }
        )
        with pytest.raises(ValidationError, match="iteration context"):
            SQLGenerator(source_table="__vd_src").generate(vd)
