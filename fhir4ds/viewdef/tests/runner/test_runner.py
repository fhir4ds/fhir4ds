"""Generic composition runner (manifest-driven) — own test suite.

The OMOP library consumes this as an EXTERNAL USER would: a synthetic
manifest exercises every primitive (materialize, union, projections,
extra join-targets) with no OMOP content.
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.runner import (
    apply_projections, compose_union, generate_view_sql,
    load_manifest, materialize_views, run_composition,
)

SRC = [
    {"resourceType": "Patient", "id": "p1", "gender": "male", "birthDate": "1974-12-25"},
    {"resourceType": "Patient", "id": "p2", "gender": "female", "birthDate": "1985-05-06"},
    {"resourceType": "Observation", "id": "o1", "status": "final",
     "code": {"coding": [{"system": "http://loinc.org", "code": "718-7"}]},
     "subject": {"reference": "Patient/p1"}, "effectiveDateTime": "2024-03-01",
     "valueQuantity": {"value": 13.5}},
    {"resourceType": "Immunization", "id": "i1", "status": "completed",
     "vaccineCode": {"coding": [{"system": "http://hl7.org/fhir/sid/cvx", "code": "140"}]},
     "patient": {"reference": "Patient/p1"}, "occurrenceDateTime": "2024-02-15"},
]


@pytest.fixture()
def family_dir(tmp_path):
    """A synthetic view family: person + two event views + a manifest."""
    d = tmp_path / "family"
    d.mkdir()
    (d / "person-view.json").write_text(json.dumps({
        "name": "f_person", "status": "draft", "resource": "Patient",
        "select": [{"column": [
            {"name": "person_id", "path": "id", "type": "id"},
            {"name": "gender", "path": "gender", "type": "code"},
        ]}],
    }))
    (d / "obs-view.json").write_text(json.dumps({
        "name": "f_obs", "status": "draft", "resource": "Observation",
        "select": [{"column": [
            {"name": "event_id", "path": "id", "type": "id"},
            {"name": "person_id", "path": "subject.reference.split('/').last()", "type": "string"},
            {"name": "code", "path": "code.coding.code.first()", "type": "code"},
        ]}],
    }))
    (d / "imm-view.json").write_text(json.dumps({
        "name": "f_imm", "status": "draft", "resource": "Immunization",
        "select": [{"column": [
            {"name": "event_id", "path": "id", "type": "id"},
            {"name": "person_id", "path": "patient.reference.split('/').last()", "type": "string"},
            {"name": "code", "path": "vaccineCode.coding.code.first()", "type": "code"},
        ]}],
    }))
    (d / "manifest.json").write_text(json.dumps({
        "views": {"person-view": "person", "obs-view": "obs", "imm-view": "imm"},
        "unions": {"events": ["obs-view", "imm-view"]},
        "projections": {
            "person": {"hash_keys": ["person_id"]},
            "events": {"hash_keys": ["person_id", "event_id"]},
        },
        "view_schema": "fam",
    }))
    return d


@pytest.fixture()
def con():
    c = fhir4ds.create_connection()
    c.execute("CREATE TABLE resources (resource JSON)")
    for r in SRC:
        c.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])
    return c


class TestPrimitives:
    def test_load_manifest_defaults(self, family_dir):
        m = load_manifest(family_dir / "manifest.json")
        assert m["unions"] and m["projections"]
        with pytest.raises(ValueError, match="views"):
            bad = family_dir / "bad.json"
            bad.write_text(json.dumps({"unions": {}}))
            load_manifest(bad)

    def test_generate_view_sql(self, family_dir):
        sql = generate_view_sql(family_dir / "person-view.json", "resources")
        assert "fhirpath_text" in sql and "'Patient'" in sql

    def test_materialize_views(self, con, family_dir):
        created = materialize_views(con, family_dir, ["person-view"], "resources", schema="fam")
        assert created == {"person-view": 'fam."person"'}
        rows = con.execute('SELECT count(*) FROM fam."person"').fetchone()[0]
        assert rows == 2

    def test_compose_union(self, con, family_dir):
        children = materialize_views(con, family_dir, ["obs-view", "imm-view"], "resources", schema="fam")
        name = compose_union(con, [children[s] for s in children], "events", schema="fam")
        n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        assert n == 2

    def test_apply_projections(self, con):
        wrapped = apply_projections(
            None, "SELECT 'p1' AS person_id, 'x' AS tag",
            ["person_id", "tag"], hash_keys=["person_id"],
        )
        row = con.execute(wrapped).fetchone()
        assert row[0] == con.execute("SELECT hash('p1') & 9223372036854775807").fetchone()[0]
        assert row[1] == "x"
        # defaults
        wrapped2 = apply_projections(
            None, "SELECT NULL AS concept_id", ["concept_id"], defaults={"concept_id": 0},
        )
        assert con.execute(wrapped2).fetchone()[0] == 0


class TestRunComposition:
    def test_full_family(self, con, family_dir):
        created = run_composition(con, family_dir / "manifest.json", "resources")
        assert set(created) - {"__join_targets__"} == {"person", "events"}
        # person hashed + referentially consistent with events
        p1 = con.execute(
            'SELECT person_id FROM fam."person" WHERE person_id IS NOT NULL LIMIT 1').fetchone()
        n = con.execute('SELECT count(*) FROM fam."events"').fetchone()[0]
        assert n == 2
        # events.person_id is the SAME hash as person.person_id for p1
        ev = con.execute(
            'SELECT DISTINCT e.person_id FROM fam."events" e '
            'JOIN fam."person" p ON p.person_id = e.person_id').fetchall()
        assert len(ev) == 1

    def test_union_column_mismatch_rejected(self, con, family_dir):
        (family_dir / "bad-view.json").write_text(json.dumps({
            "name": "f_bad", "resource": "Patient",
            "select": [{"column": [{"name": "only_one", "path": "id", "type": "id"}]}],
        }))
        m = json.loads((family_dir / "manifest.json").read_text())
        m["unions"]["events"] = ["obs-view", "bad-view"]
        (family_dir / "manifest.json").write_text(json.dumps(m))
        with pytest.raises(ValueError, match="column mismatch"):
            run_composition(con, family_dir / "manifest.json", "resources")

    def test_materialize_override(self, con, family_dir):
        # 'materialize' is an OVERRIDE/hint: eager materialization under a
        # custom name (e.g. a view nothing joins yet). Correctness never
        # depends on it.
        m = json.loads((family_dir / "manifest.json").read_text())
        m["materialize"] = {"genders": "person-view"}
        (family_dir / "manifest.json").write_text(json.dumps(m))
        created = run_composition(con, family_dir / "manifest.json", "resources")
        n = con.execute('SELECT count(*) FROM fam."genders"').fetchone()[0]
        assert n == 2

    def test_dependency_inference_zero_config(self, con, family_dir):
        # A VD that view-joins another library VD: materialization order is
        # INFERRED (join target first) with NO manifest materialize entry.
        (family_dir / "codes-view.json").write_text(json.dumps({
            "name": "f_codes", "resource": "Patient",
            "select": [{"column": [
                {"name": "code", "path": "gender", "type": "code"},
            ]}],
        }))
        (family_dir / "by-code-view.json").write_text(json.dumps({
            "name": "f_by_code", "resource": "Patient",
            "select": [{"column": [
                {"name": "person_id", "path": "id", "type": "id"},
                {"name": "joined_code", "path": "c.code", "type": "code"},
            ]}],
            "joins": [{
                "name": "c", "view": "f_codes", "type": "left",
                "on": [{"path": "gender"}, {"path": "c.code"}],
            }],
        }))
        m = json.loads((family_dir / "manifest.json").read_text())
        m["views"]["codes-view"] = "codes"
        m["views"]["by-code-view"] = "by-code"
        (family_dir / "manifest.json").write_text(json.dumps(m))
        created = run_composition(con, family_dir / "manifest.json", "resources")
        # the join target materialized (inferred), the consumer composed
        rows = con.execute('SELECT * FROM fam."by_code" ORDER BY 1').fetchall()
        assert rows == [("p1", "male"), ("p2", "female")]

    def test_dependency_cycle_rejected(self, con, family_dir):
        (family_dir / "a-view.json").write_text(json.dumps({
            "name": "f_a", "resource": "Patient",
            "select": [{"column": [{"name": "id", "path": "id", "type": "id"},
                                    {"name": "x", "path": "b.id", "type": "id"}]}],
            "joins": [{"name": "b", "view": "f_b", "type": "left",
                       "on": [{"path": "id"}, {"path": "b.id"}]}],
        }))
        (family_dir / "b-view.json").write_text(json.dumps({
            "name": "f_b", "resource": "Patient",
            "select": [{"column": [{"name": "id", "path": "id", "type": "id"},
                                    {"name": "x", "path": "a.id", "type": "id"}]}],
            "joins": [{"name": "a", "view": "f_a", "type": "left",
                       "on": [{"path": "id"}, {"path": "a.id"}]}],
        }))
        m = json.loads((family_dir / "manifest.json").read_text())
        m["views"]["a-view"] = "a"
        m["views"]["b-view"] = "b"
        (family_dir / "manifest.json").write_text(json.dumps(m))
        with pytest.raises(ValueError, match="cycle"):
            run_composition(con, family_dir / "manifest.json", "resources")

    def test_unknown_view_target_rejected(self, con, family_dir):
        (family_dir / "bad-join-view.json").write_text(json.dumps({
            "name": "f_bad_join", "resource": "Patient",
            "select": [{"column": [{"name": "id", "path": "id", "type": "id"}]}],
            "joins": [{"name": "z", "view": "nonexistent", "type": "left",
                       "on": [{"path": "id"}, {"path": "z.id"}]}],
        }))
        m = json.loads((family_dir / "manifest.json").read_text())
        m["views"]["bad-join-view"] = "bad_join"
        (family_dir / "manifest.json").write_text(json.dumps(m))
        with pytest.raises(ValueError, match="nonexistent"):
            run_composition(con, family_dir / "manifest.json", "resources")


class TestPureTextRendering:
    """The browser path: plan + render_view_sqls + render_composition_ddl.

    Mirrors the Viewing Room worker's live composition: Pyodide produces
    all SQL text; the connecting layer executes plain view CREATEs and
    introspects columns; the pure renderer emits the remaining DDL. The
    resulting schema must match run_composition exactly.
    """

    def test_text_rendering_matches_connection_composition(self, con, family_dir):
        from fhir4ds.viewdef.runner import (
            build_composition_plan, render_view_sqls, render_composition_ddl,
        )

        # Reference: the connection-driven composition.
        run_composition(con, family_dir / "manifest.json", "resources")
        expected = {}
        for name in ("person", "events"):
            expected[name] = con.execute(
                f'SELECT * FROM fam."{name}" ORDER BY 1'
            ).fetchall()

        # Text-only path on a fresh connection.
        con2 = fhir4ds.create_connection()
        con2.execute("CREATE TABLE resources (resource JSON)")
        for r in SRC:
            con2.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])

        manifest_path = family_dir / "manifest.json"
        plan = build_composition_plan(manifest_path)
        con2.execute(f'CREATE SCHEMA IF NOT EXISTS {plan["schema"]}')
        columns = {}
        for view in render_view_sqls(plan, family_dir, "resources"):
            con2.execute(f'CREATE OR REPLACE VIEW {view["table_sql"]} AS\n{view["sql"]}')
            columns[view["name"]] = [
                d[0] for d in con2.execute(
                    f'SELECT * FROM {view["table_sql"]} LIMIT 0').description
            ]
        sqls = {v["name"]: v["sql"] for v in render_view_sqls(plan, family_dir, "resources")}
        for stmt in render_composition_ddl(plan, columns, sql_by_view=sqls):
            con2.execute(stmt)

        for name, rows in expected.items():
            got = con2.execute(f'SELECT * FROM fam."{name}" ORDER BY 1').fetchall()
            assert got == rows, f"{name} differs between connection and text paths"

    def test_render_rejects_missing_columns(self, family_dir):
        import pytest as _pytest
        from fhir4ds.viewdef.runner import build_composition_plan, render_composition_ddl

        plan = build_composition_plan(family_dir / "manifest.json")
        with _pytest.raises(ValueError, match="missing columns"):
            render_composition_ddl(plan, {}, sql_by_view={})
