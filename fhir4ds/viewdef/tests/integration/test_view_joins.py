"""View-as-join-target (rev 2, S6a): Join.view root joins.

The join target is a MATERIALIZED VIEW (another ViewDefinition's flat
output) per the spec's composition semantics — SQLView-notes: "each
referenced result acts as a virtual table for the referencing query";
"The executing engine may materialise the view's result or inline it;
either approach conforms to this specification."

Pins: parse/validate (view vs resource exclusivity), column-ref routing
(alias.column paths emit SQL column references, not FHIRPath), ON pairs
comparing base FHIRPath to view columns, table resolution (view_tables
map + schema convention), and the monolithic-ConceptMap → flattened
view → event join chain that replaces the element-per-resource form.
"""

import json

import pytest

import fhir4ds
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator
from fhir4ds.viewdef.errors import ValidationError


MONOLITHIC_CONCEPTMAP = {
    "resourceType": "ConceptMap", "id": "supplements", "status": "active",
    "group": [
        {"source": "http://hl7.org/fhir/administrative-gender", "element": [
            {"code": "male", "target": [{"code": "8507", "equivalence": "equivalent"}]},
            {"code": "female", "target": [{"code": "8532", "equivalence": "equivalent"}]}]},
        {"source": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "element": [
            {"code": "IMP", "target": [{"code": "9201", "equivalence": "equivalent"}]},
            {"code": "AMB", "target": [{"code": "9202", "equivalence": "equivalent"}]}]},
    ],
}

PERSON_VIEW_JOIN = {
    "resource": "Patient",
    "select": [{"column": [
        {"name": "person_id", "path": "id", "type": "id"},
        {"name": "gender_concept_id", "path": "cm.concept_id", "type": "string"},
        {"name": "gender_source_value", "path": "gender", "type": "code"},
    ]}],
    "joins": [{
        "name": "cm", "view": "omop_conceptmap", "type": "left",
        "on": [{"path": "gender"}, {"path": "cm.concept_code"}],
    }],
}

# Flattening VD in the S1 conceptmap-view SHAPE: vocabulary at group level,
# concept_code at element level, concept_id at target level (cross-product
# semantics give exactly one row per mapping; %resource re-navigation from
# nested scopes would cross-match ALL elements — the scoping lesson).
CONCEPTMAP_VD = {
    "resource": "ConceptMap",
    "select": [
        {"forEach": "group", "select": [
            {"forEach": "element", "column": [
                {"name": "concept_code", "path": "code", "type": "string"},
            ], "select": [
                {"forEach": "target", "column": [
                    {"name": "concept_id", "path": "code", "type": "string"},
                ]},
            ]},
        ], "column": [
            {"name": "vocabulary_id", "path": "source", "type": "string"},
        ]},
    ],
}


@pytest.fixture()
def conn():
    con = fhir4ds.create_connection()
    con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
    con.execute("CREATE SCHEMA IF NOT EXISTS omop")
    # flatten the monolithic ConceptMap via a VD, materialize as a view
    cm_vd = parse_view_definition(CONCEPTMAP_VD)
    cm_sql = SQLGenerator(source_table="resources").generate(cm_vd)
    con.execute(f"CREATE OR REPLACE VIEW omop.omop_conceptmap AS\n{cm_sql}")
    return con


class TestJoinViewParsing:
    def test_view_target_parses(self):
        vd = parse_view_definition(PERSON_VIEW_JOIN)
        assert vd.joins[0].view == "omop_conceptmap"
        assert vd.joins[0].resource == ""

    def test_resource_and_view_mutually_exclusive(self):
        with pytest.raises(Exception, match="both"):
            parse_view_definition({
                **PERSON_VIEW_JOIN,
                "joins": [{**PERSON_VIEW_JOIN["joins"][0], "resource": "ConceptMap"}],
            })

    def test_neither_rejected(self):
        bad = {**PERSON_VIEW_JOIN}
        bad["joins"] = [{k: v for k, v in PERSON_VIEW_JOIN["joins"][0].items() if k not in ("view",)}]
        bad["joins"][0].pop("resource", None)
        with pytest.raises(Exception, match="resource.*or.*view|view.*or.*resource"):
            parse_view_definition(bad)

    def test_roundtrip(self):
        vd = parse_view_definition(PERSON_VIEW_JOIN)
        d = vd.joins[0].to_dict()
        assert d["view"] == "omop_conceptmap" and "resource" not in d


class TestViewJoinEmission:
    def test_column_ref_not_fhirpath(self):
        vd = parse_view_definition(PERSON_VIEW_JOIN)
        sql = SQLGenerator(source_table="resources").generate(vd)
        assert '"cm"."concept_id"' in sql
        # the column ref must NOT be wrapped in a fhirpath UDF call
        import re
        assert not re.search(r"fhirpath_text\(\s*\"cm\"", sql)

    def test_on_compares_projection_to_column(self):
        vd = parse_view_definition(PERSON_VIEW_JOIN)
        sql = SQLGenerator(source_table="resources").generate(vd)
        assert "fhirpath_text(t.resource, 'gender')" in sql
        assert 'NULLIF("cm"."concept_code"' in sql or '"cm"."concept_code"' in sql

    def test_default_schema_convention(self):
        vd = parse_view_definition(PERSON_VIEW_JOIN)
        sql = SQLGenerator(source_table="resources").generate(vd)
        assert 'LEFT JOIN "omop"."omop_conceptmap"' in sql

    def test_view_tables_map_overrides(self):
        gen = SQLGenerator(source_table="resources")
        gen._view_tables = {"omop_conceptmap": '"my_schema"."cm_flat"'}
        vd = parse_view_definition(PERSON_VIEW_JOIN)
        sql = gen.generate(vd)
        assert 'LEFT JOIN "my_schema"."cm_flat"' in sql

    def test_where_can_reference_view_column(self):
        con = fhir4ds.create_connection()
        con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
        con.execute("CREATE SCHEMA IF NOT EXISTS omop")
        cm_vd = parse_view_definition(CONCEPTMAP_VD)
        con.execute(f"CREATE OR REPLACE VIEW omop.omop_conceptmap AS\n"
                    f"{SQLGenerator(source_table='resources').generate(cm_vd)}")
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(MONOLITHIC_CONCEPTMAP)])
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(
            {"resourceType": "Patient", "id": "p1", "gender": "male"})])
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(
            {"resourceType": "Patient", "id": "p2", "gender": "unknown"})])
        vd = parse_view_definition({
            **PERSON_VIEW_JOIN,
            "where": [{"path": "cm.concept_id = '8507'"}],
        })
        sql = SQLGenerator(source_table="resources").generate(vd)
        rows = con.execute(sql).fetchall()
        assert [r[0] for r in rows] == ["p1"]


class TestMonolithicChain:
    """The rev-2 chain: monolithic ConceptMap → flattened view → event join."""

    def test_person_gender_resolution(self, conn):
        conn.execute("INSERT INTO resources VALUES (?)", [json.dumps(MONOLITHIC_CONCEPTMAP)])
        conn.execute("INSERT INTO resources VALUES (?)", [json.dumps(
            {"resourceType": "Patient", "id": "p1", "gender": "male", "birthDate": "1974-12-25"})])
        conn.execute("INSERT INTO resources VALUES (?)", [json.dumps(
            {"resourceType": "Patient", "id": "p2", "gender": "female", "birthDate": "1985-05-06"})])
        vd = parse_view_definition(PERSON_VIEW_JOIN)
        sql = SQLGenerator(source_table="resources").generate(vd)
        rows = sorted(conn.execute(sql).fetchall())
        assert rows == [("p1", "8507", "male"), ("p2", "8532", "female")]

    def test_unmatched_left_join_keeps_row(self, conn):
        conn.execute("INSERT INTO resources VALUES (?)", [json.dumps(MONOLITHIC_CONCEPTMAP)])
        conn.execute("INSERT INTO resources VALUES (?)", [json.dumps(
            {"resourceType": "Patient", "id": "p3", "gender": "other"})])
        vd = parse_view_definition(PERSON_VIEW_JOIN)
        rows = conn.execute(
            SQLGenerator(source_table="resources").generate(vd)).fetchall()
        assert rows == [("p3", None, "other")]

    def test_duplicate_alias_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate join name"):
            parse_and_gen_twice()

    def test_base_alias_conflict_rejected(self):
        vd = parse_view_definition({
            **PERSON_VIEW_JOIN,
            "joins": [{**PERSON_VIEW_JOIN["joins"][0], "name": "t"}],
        })
        with pytest.raises(ValidationError, match="base table alias"):
            SQLGenerator(source_table="resources").generate(vd)


def parse_and_gen_twice():
    vd = parse_view_definition({
        **PERSON_VIEW_JOIN,
        "joins": [PERSON_VIEW_JOIN["joins"][0], PERSON_VIEW_JOIN["joins"][0]],
    })
    return SQLGenerator(source_table="resources").generate(vd)


class TestViewJoinReviewHardening:
    """Release v0.0.19 code-review hardening: identifier validation on
    view-column references (columns + ON sides) and typed rejection of
    mixed view+base where expressions (previously emitted an operand that
    could not bind, surfacing as an opaque execution error)."""

    def test_view_column_reference_validates_identifier(self):
        from fhir4ds.viewdef.errors import ValidationError
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{"column": [
                {"name": "x", "path": "cm.concept_id", "type": "string"},
            ]}],
            "joins": [{"name": "cm", "view": "omop_conceptmap", "type": "left",
                       "on": [{"path": "gender"}, {"path": "cm.vocabulary_id"}]}],
        })
        sql = SQLGenerator(source_table="resources").generate(vd)
        assert '"cm"."concept_id"' in sql

    def test_mixed_view_base_where_rejected_typed(self):
        from fhir4ds.viewdef.errors import ValidationError
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{"column": [{"name": "id", "path": "id"}]}],
            "where": [{"path": "cm.concept_id = gender"}],
            "joins": [{"name": "cm", "view": "omop_conceptmap", "type": "left",
                       "on": [{"path": "gender"}, {"path": "cm.vocabulary_id"}]}],
        })
        with pytest.raises(ValidationError, match="mixes view-join columns"):
            SQLGenerator(source_table="resources").generate(vd)

    def test_view_column_vs_literal_where_still_works(self):
        vd = parse_view_definition({
            "resource": "Patient",
            "select": [{"column": [{"name": "id", "path": "id"}]}],
            "where": [{"path": "cm.concept_id = '8507'"}],
            "joins": [{"name": "cm", "view": "omop_conceptmap", "type": "left",
                       "on": [{"path": "gender"}, {"path": "cm.vocabulary_id"}]}],
        })
        sql = SQLGenerator(source_table="resources").generate(vd)
        assert "\"cm\".\"concept_id\" = '8507'" in sql
