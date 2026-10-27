"""The browser-side key projection must match the composition's keys.

The Viewing Room runs one ViewDefinition (or an author's SQLQuery) and then
wraps the result with ``omop_key_projection_sql`` so the demo shows the
same BIGINT surrogate keys the composed tables carry. That wrapper has two
constraints the composition path does not: the query may project a subset
of the table's columns, and it must not invent keys for NULL ids.
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.omop_runner import create_omop_views, omop_key_projection_sql
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

OMOP_DIR = Path(__file__).parents[2] / "resources" / "omop"
MASK = 9223372036854775807


@pytest.fixture()
def con():
    con = fhir4ds.create_connection()
    con.execute(
        "CREATE TABLE raw AS SELECT * FROM (VALUES "
        "('p1', '8507', 'male', NULL), "
        "('p2', NULL, 'female', 'v-2')) "
        "v(person_id, gender_concept_id, gender_source_value, gender_source_concept_id)"
    )
    return con


def test_hashes_are_the_composition_hash(con):
    sql = omop_key_projection_sql(
        "person", "SELECT * FROM raw", ["person_id", "gender_concept_id"]
    )
    got = dict(con.execute(f"SELECT person_id, person_id FROM ({sql})").fetchall())
    for key in ("p1", "p2"):
        expected = con.execute(
            f"SELECT CAST(hash('{key}') & {MASK} AS BIGINT)"
        ).fetchone()[0]
        assert got[expected] == expected


def test_null_keys_stay_null(con):
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('p1'), (NULL)) v(person_id)")
    sql = omop_key_projection_sql("person", "SELECT * FROM t", ["person_id"])
    rows = con.execute(sql).fetchall()
    assert len(rows) == 2
    assert sorted(r[0] is None for r in rows) == [False, True]


def test_defaults_fill_missing_concepts(con):
    sql = omop_key_projection_sql(
        "person",
        "SELECT * FROM raw",
        ["person_id", "gender_concept_id", "gender_source_value"],
    )
    rows = con.execute(
        f"SELECT gender_concept_id FROM ({sql}) ORDER BY gender_source_value"
    ).fetchall()
    assert [r[0] for r in rows] == [0, 8507]


def test_subset_columns_do_not_error(con):
    # A SQLQuery may project only some of drug_exposure's key columns; the
    # wrapper must skip the ones it cannot see rather than fail.
    con.execute(
        "CREATE TABLE d AS SELECT 'm1' AS drug_exposure_id, '19009384' AS drug_concept_id, 'x' AS drug_source_value"
    )
    sql = omop_key_projection_sql(
        "drug_exposure",
        "SELECT * FROM d",
        ["drug_exposure_id", "drug_concept_id", "drug_source_value"],
    )
    row = con.execute(sql).fetchone()
    assert row[0] == con.execute(
        f"SELECT CAST(hash('m1') & {MASK} AS BIGINT)"
    ).fetchone()[0]
    assert row[1] == 19009384


def test_unknown_table_is_passthrough():
    inner = "SELECT 1 AS x"
    assert omop_key_projection_sql("not_a_table", inner, ["x"]) == inner


def test_matches_the_composed_person_table(con):
    # End to end: raw patient resources -> (a) composed omop.person and
    # (b) the person view + wrapper the browser runs. Same ids both ways.
    con.execute("CREATE TABLE resources (resource JSON)")
    for line in (OMOP_DIR / "demo" / "resources.ndjson").read_text().splitlines():
        if line.strip():
            con.execute("INSERT INTO resources VALUES (?)", [line.strip()])
    create_omop_views(con, source_table="resources")
    composed = set(
        r[0] for r in con.execute("SELECT person_id FROM omop.person").fetchall()
    )

    vd = parse_view_definition(json.loads((OMOP_DIR / "person-view.json").read_text()))
    gen = SQLGenerator(source_table="resources")
    gen.view_schema = "omop"
    raw_sql = gen.generate(vd)
    columns = [
        d[0] for d in con.execute(f"SELECT * FROM ({raw_sql}) LIMIT 0").description
    ]
    projected = set(
        r[0]
        for r in con.execute(
            omop_key_projection_sql("person", raw_sql, columns)
        ).fetchall()
    )
    assert composed == projected
