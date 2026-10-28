"""The SQLQuery composition must not renumber OMOP keys.

Person moved from a ViewDefinition `joins` block + manifest projection to a
plain reshape + SQLQuery (join + hash). These ids are the ones the previous
implementation produced for the demo fixture, so the migration is behaviour
preserving.
"""

from pathlib import Path

import fhir4ds
from fhir4ds.viewdef.omop_runner import create_omop_views

OMOP_DIR = Path(__file__).parents[2] / "resources" / "omop"


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
