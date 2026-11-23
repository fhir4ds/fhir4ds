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
        # AMUX-152 #27: schema is quoted now ('"fam"' ≡ fam in DuckDB)
        assert created == {"person-view": '"fam"."person"'}
        rows = con.execute('SELECT count(*) FROM fam."person"').fetchone()[0]
        assert rows == 2

    def test_compose_union(self, con, family_dir):
        # AMUX-152 #27: compose_union takes BARE child names (quoted inside)
        children = materialize_views(con, family_dir, ["obs-view", "imm-view"], "resources", schema="fam")
        stems = ["obs-view", "imm-view"]
        name = compose_union(con, [s.replace("-view", "").replace("-", "_") for s in stems], "events", schema="fam")
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


class TestQuotingRoundTripAmux152:
    """AMUX-152 #27: identifiers needing quoting (mixed case, spaces,
    reserved words) round-trip through the runner primitives."""

    def test_materialize_views_quoting_needing_identifiers(self, con, family_dir):
        created = materialize_views(
            con, family_dir, ["person-view"], "resources",
            schema="My Schema", table_name="order",
        )
        assert created == {"person-view": '"My Schema"."order"'}
        rows = con.execute('SELECT count(*) FROM "My Schema"."order"').fetchone()[0]
        assert rows == 2

    def test_compose_union_quoting_needing_identifiers(self, con, family_dir):
        # distinct quoting-needing names per child (table_name is shared
        # across stems, so materialize one at a time)
        materialize_views(con, family_dir, ["obs-view"], "resources",
                          schema="My Schema", table_name="select all")
        materialize_views(con, family_dir, ["imm-view"], "resources",
                          schema="My Schema", table_name="group by")
        ref = compose_union(con, ["select all", "group by"], "full join", schema="My Schema")
        assert ref == '"My Schema"."full join"'
        n = con.execute(f"SELECT count(*) FROM {ref}").fetchone()[0]
        assert n == 2

    def test_projection_sql_quotes_columns_and_coerces_defaults(self):
        from fhir4ds.viewdef.runner import _projection_sql
        sql = _projection_sql(
            "SELECT 1 AS \"order\", NULL AS \"visit id\"",
            ["order", "visit id"],
            hash_keys=["order"],
            defaults={"visit id": 0},
        )
        assert '"order"' in sql and '"visit id"' in sql
        # hash/TRY_CAST reference the QUOTED column names
        assert 'hash("order")' in sql
        assert 'TRY_CAST("visit id" AS BIGINT), 0)' in sql

    def test_run_composition_quoting_needing_schema(self, con, family_dir):
        # rewrite the manifest with a quoting-needing view_schema
        m = json.loads((family_dir / "manifest.json").read_text())
        m["view_schema"] = "OMOP Schema"
        (family_dir / "manifest.json").write_text(json.dumps(m))
        created = run_composition(con, family_dir / "manifest.json", "resources")
        ref = created["events"]
        assert ref == '"OMOP Schema"."events"'
        n = con.execute(f"SELECT count(*) FROM {ref}").fetchone()[0]
        assert n == 2

    def test_render_pipeline_parity_quoting_needing_schema(self, con, family_dir):
        """D5-SKEPTIC v0.0.26: the text-render pipeline (render_view_sqls +
        render_composition_ddl — the browser worker's path) must produce the
        same rowsets as run_composition under a quoting-needing schema."""
        from fhir4ds.viewdef.runner import (
            build_composition_plan, render_view_sqls, render_composition_ddl,
        )
        m = json.loads((family_dir / "manifest.json").read_text())
        m["view_schema"] = "OMOP Schema"
        (family_dir / "manifest.json").write_text(json.dumps(m))

        con_exec = fhir4ds.create_connection()
        con_exec.execute("CREATE TABLE resources (resource JSON)")
        from .test_runner import SRC as _SRC
        for r in _SRC:
            con_exec.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])
        run_composition(con_exec, family_dir / "manifest.json", "resources")

        plan = build_composition_plan(family_dir / "manifest.json")
        con_ren = fhir4ds.create_connection()
        con_ren.execute("CREATE TABLE resources (resource JSON)")
        for r in _SRC:
            con_ren.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])
        con_ren.execute(f'CREATE SCHEMA IF NOT EXISTS "{plan["schema"]}"')
        views = render_view_sqls(plan, family_dir, "resources")
        columns, sqls = {}, {}
        for v in views:
            con_ren.execute(f'CREATE OR REPLACE VIEW {v["table_sql"]} AS\n{v["sql"]}')
            columns[v["name"]] = [
                c[0] for c in con_ren.execute(
                    f'SELECT * FROM {v["table_sql"]} LIMIT 0').description
            ]
            sqls[v["name"]] = v["sql"]
        for stmt in render_composition_ddl(plan, columns, sql_by_view=sqls):
            con_ren.execute(stmt)

        for table in ("person", "events"):
            a = sorted(map(str, con_exec.execute(
                f'SELECT * FROM "OMOP Schema"."{table}"').fetchall()))
            b = sorted(map(str, con_ren.execute(
                f'SELECT * FROM "OMOP Schema"."{table}"').fetchall()))
            assert a == b and a, f"{table}: exec={a} render={b}"


class TestEvolV0026D5Historian:
    """D5-HISTORIAN v0.0.26 walkthrough findings.

    QA-D5H-001: manifests of nameless ViewDefinitions (name is 0..1 per the
    published StructureDefinition) crashed build_composition_plan with a raw
    KeyError, and duplicate VD names crashed the same way — the planner keyed
    identity by vd.name with no presence/uniqueness handling.

    QA-D5H-002: the text-render pipeline (render_view_sqls pass 1 +
    render_composition_ddl pass 2 — the browser worker's path) emitted
    SQLQuery CREATEs in pass 1, BEFORE union tables exist (pass 2), so a
    SQLQuery reading a union-family table Catalog-errored on the render path
    while the exec path (run_composition) ordered it correctly.
    """

    def test_nameless_vds_compose_and_duplicate_names_are_typed(self, con, tmp_path):
        from fhir4ds.viewdef.runner import build_composition_plan, run_composition

        d = tmp_path / "nameless"
        d.mkdir()
        vd = {"resource": "Patient",
              "select": [{"column": [{"name": "pid", "path": "id"}]}]}
        for stem in ("a-view", "b-view"):
            (d / f"{stem}.json").write_text(json.dumps(vd))
        (d / "manifest.json").write_text(json.dumps(
            {"views": {"a-view": "a", "b-view": "b"}}))

        # Two nameless VDs must compose (was: KeyError 'a-view').
        created = run_composition(con, d / "manifest.json", "resources")
        rows_a = con.execute('SELECT pid FROM "omop"."a" ORDER BY pid').fetchall()
        rows_b = con.execute('SELECT pid FROM "omop"."b" ORDER BY pid').fetchall()
        assert rows_a == rows_b == [("p1",), ("p2",)]
        assert created["a"] == '"omop"."a"'

        # Duplicate DECLARED names are a typed ambiguity error (was KeyError).
        named = {"resource": "Patient", "name": "Dup",
                 "select": [{"column": [{"name": "pid", "path": "id"}]}]}
        (d / "a-view.json").write_text(json.dumps(named))
        (d / "b-view.json").write_text(json.dumps(named))
        with pytest.raises(ValueError, match="Duplicate ViewDefinition name 'Dup'"):
            build_composition_plan(d / "manifest.json")

    def test_render_pipeline_sqlquery_over_union_parity(self, tmp_path):
        """A SQLQuery that reads a union-family table must compose on the
        text-render pipeline exactly like run_composition (was: render pass 1
        created the SQLQuery before the union table existed -> Catalog Error)."""
        import base64
        from fhir4ds.viewdef.runner import (
            build_composition_plan, run_composition,
            render_view_sqls, render_composition_ddl,
        )

        d = tmp_path / "unionquery"
        d.mkdir()
        (d / "arm-view.json").write_text(json.dumps({
            "name": "Arm", "resource": "Patient",
            "select": [{"column": [{"name": "pid", "path": "id"}]}],
        }))
        (d / "sqlqueries").mkdir()
        (d / "sqlqueries" / "final.json").write_text(json.dumps({
            "resourceType": "Library",
            "content": [{"contentType": "application/sql",
                         "data": base64.b64encode(b"SELECT pid FROM omop.fam").decode()}],
        }))
        (d / "manifest.json").write_text(json.dumps({
            "views": {"arm-view": "arm"},
            "unions": {"fam": ["arm-view"]},
            "sql_queries": {"final": "final"},
        }))

        def fresh():
            c = fhir4ds.create_connection()
            c.execute("CREATE TABLE resources (resource JSON)")
            for r in SRC:
                c.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])
            return c

        con_exec = fresh()
        run_composition(con_exec, d / "manifest.json", "resources")
        expected = con_exec.execute('SELECT pid FROM omop."final" ORDER BY pid').fetchall()
        assert expected == [("p1",), ("p2",)]

        plan = build_composition_plan(d / "manifest.json")
        con_ren = fresh()
        con_ren.execute('CREATE SCHEMA IF NOT EXISTS "omop"')
        columns, sqls = {}, {}
        for v in render_view_sqls(plan, d, "resources"):
            con_ren.execute(f'CREATE OR REPLACE VIEW {v["table_sql"]} AS\n{v["sql"]}')
            columns[v["name"]] = [
                c[0] for c in con_ren.execute(
                    f'SELECT * FROM {v["table_sql"]} LIMIT 0').description]
            sqls[v["name"]] = v["sql"]
        # union children must be introspectable for the union step
        for step in plan["steps"]:
            if step["type"] == "union":
                for child in step["children"]:
                    columns.setdefault(child, columns.get("arm"))
        for stmt in render_composition_ddl(plan, columns, sql_by_view=sqls):
            con_ren.execute(stmt)
        got = con_ren.execute('SELECT pid FROM omop."final" ORDER BY pid').fetchall()
        assert got == expected, f"render={got} exec={expected}"


class TestEvolV0026D5Explorer:
    """D5-EXPLORER v0.0.26 fuzz findings.

    QA-D5E-001 (MEDIUM): the composition planner normalized distinct manifest
    stems / union / SQLQuery tables onto ONE output table with no uniqueness
    check, so run_composition silently last-wins (CREATE OR REPLACE shadows
    an earlier step) and a SQLQuery colliding with a VD view created a
    self-referential view (raw DuckDB BinderException "infinite recursion
    detected" at select time). build_composition_plan now rejects any two
    steps that would write the same output table with a typed ValueError.
    """

    def _vd(self, src_literal):
        return {
            "resource": "Patient",
            "select": [{"column": [
                {"name": "id", "path": "id"},
                {"name": "src", "path": f"'{src_literal}'"},
            ]}],
        }

    def test_stem_normalization_collision_is_typed_error(self, tmp_path):
        import pytest
        from fhir4ds.viewdef.runner import build_composition_plan
        d = tmp_path / "collide"
        d.mkdir()
        (d / "a-b-view.json").write_text(json.dumps(self._vd("hyphen")))
        (d / "a.b-view.json").write_text(json.dumps(self._vd("dot")))
        (d / "manifest.json").write_text(json.dumps(
            {"views": {"a-b-view": "", "a.b-view": ""}}))
        with pytest.raises(ValueError, match="a_b"):
            build_composition_plan(d / "manifest.json")

    def test_union_table_vs_single_stem_collision_is_typed_error(self, tmp_path):
        import pytest
        from fhir4ds.viewdef.runner import build_composition_plan
        d = tmp_path / "ucoll"
        d.mkdir()
        (d / "fam-a-view.json").write_text(json.dumps(self._vd("arm")))
        (d / "fam-b-view.json").write_text(json.dumps(self._vd("arm")))
        (d / "fam-view.json").write_text(json.dumps(self._vd("single")))
        (d / "manifest.json").write_text(json.dumps({
            "views": {"fam-a-view": "", "fam-b-view": "", "fam-view": ""},
            "unions": {"fam": ["fam-a-view", "fam-b-view"]},
        }))
        # previously the 'single' step silently OVERWROTE the union table
        with pytest.raises(ValueError, match="fam"):
            build_composition_plan(d / "manifest.json")

    def test_sqlquery_table_vs_view_collision_is_typed_error(self, tmp_path):
        import base64
        import pytest
        from fhir4ds.viewdef.runner import build_composition_plan
        d = tmp_path / "sqcoll"
        d.mkdir()
        (d / "person-view.json").write_text(json.dumps({
            "resource": "Patient",
            "select": [{"column": [{"name": "id", "path": "id"}]}],
        }))
        (d / "sqlqueries").mkdir()
        (d / "sqlqueries" / "dup.json").write_text(json.dumps({
            "resourceType": "Library",
            "content": [{"contentType": "application/sql",
                         "data": base64.b64encode(
                             b"SELECT id FROM omop.person").decode()}],
        }))
        (d / "manifest.json").write_text(json.dumps({
            "views": {"person-view": ""},
            "sql_queries": {"person": "dup"},
        }))
        # previously created a self-referential view (BinderException at select)
        with pytest.raises(ValueError, match="person"):
            build_composition_plan(d / "manifest.json")

    def test_distinct_output_tables_still_compose(self, tmp_path):
        """Control: non-colliding stems (incl. unicode + quoting-needing
        schema + unions + sqlquery) still plan and execute end-to-end."""
        import base64
        import fhir4ds
        from fhir4ds.viewdef.runner import run_composition
        d = tmp_path / "ok"
        d.mkdir()
        (d / "persön-view.json").write_text(json.dumps(self._vd("u")))
        (d / "we-ird-view.json").write_text(json.dumps(self._vd("q")))
        (d / "sqlqueries").mkdir()
        (d / "sqlqueries" / "reader.json").write_text(json.dumps({
            "resourceType": "Library",
            "content": [{"contentType": "application/sql",
                         "data": base64.b64encode(
                             b'SELECT id FROM "My Schema"."uni table"').decode()}],
        }))
        (d / "manifest.json").write_text(json.dumps({
            "views": {"persön-view": "", "we-ird-view": ""},
            "view_schema": "My Schema",
            "unions": {"uni table": ["persön-view", "we-ird-view"]},
            "sql_queries": {"reader": "reader"},
        }))
        con = fhir4ds.create_connection()
        con.execute("CREATE TABLE resources (resource JSON)")
        for r in SRC:
            con.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])
        run_composition(con, d / "manifest.json", "resources")
        n = con.execute('SELECT count(*) FROM "My Schema"."reader"').fetchone()[0]
        assert n == 4  # 2 arms x 2 patients
