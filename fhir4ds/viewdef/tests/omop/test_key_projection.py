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
        "('v1', 'p1', '9202', 'AMB'), "
        "('v2', 'p2', NULL, 'IMP')) "
        "v(visit_occurrence_id, person_id, visit_concept_id, visit_source_value)"
    )
    return con


def test_hashes_are_the_composition_hash(con):
    sql = omop_key_projection_sql(
        "visit_occurrence",
        "SELECT * FROM raw",
        ["visit_occurrence_id", "person_id", "visit_concept_id"],
    )
    # Order by the source column, not the hashed key, so the pairing is
    # (v1,p1), (v2,p2) regardless of hash magnitude.
    rows = con.execute(
        f"SELECT visit_occurrence_id, person_id FROM ({sql}) ORDER BY visit_source_value"
    ).fetchall()
    for row, visit_key, person_key in zip(rows, ("v1", "v2"), ("p1", "p2")):
        assert row[0] == con.execute(
            f"SELECT CAST(hash('{visit_key}') & {MASK} AS BIGINT)"
        ).fetchone()[0]
        assert row[1] == con.execute(
            f"SELECT CAST(hash('{person_key}') & {MASK} AS BIGINT)"
        ).fetchone()[0]


def test_null_keys_stay_null(con):
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('p1'), (NULL)) v(person_id)")
    sql = omop_key_projection_sql("death", "SELECT * FROM t", ["person_id"])
    rows = con.execute(sql).fetchall()
    assert len(rows) == 2
    assert sorted(r[0] is None for r in rows) == [False, True]


def test_defaults_fill_missing_concepts(con):
    sql = omop_key_projection_sql(
        "visit_occurrence",
        "SELECT * FROM raw",
        ["visit_occurrence_id", "person_id", "visit_concept_id", "visit_source_value"],
    )
    rows = con.execute(
        f"SELECT visit_concept_id FROM ({sql}) ORDER BY visit_source_value"
    ).fetchall()
    assert [r[0] for r in rows] == [9202, 0]


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


def test_sqlquery_person_matches_the_composed_table():
    """The person SQLQuery reproduces the keys the composition hashed.

    Person moved from a ViewDefinition `joins` + manifest projection to a
    plain reshape + SQLQuery (join + hash). These ids are the ones the
    previous implementation produced for the demo fixture: the migration
    must not renumber patients.
    """
    con = fhir4ds.create_connection()
    con.execute("CREATE TABLE resources (resource JSON)")
    for line in (OMOP_DIR / "demo" / "resources.ndjson").read_text().splitlines():
        if line.strip():
            con.execute("INSERT INTO resources VALUES (?)", [line.strip()])
    create_omop_views(con, source_table="resources")
    pairs = con.execute(
        "SELECT person_id, person_source_value FROM omop.person ORDER BY person_source_value"
    ).fetchall()
    assert pairs == [
        (6019492087770420870, "pat-001"),
        (4634691128028980087, "pat-002"),
    ]
