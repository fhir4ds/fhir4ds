"""The append-only log, its latest-wins view, and the patient-reference rule."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.serve.versioning import (
    BASE_TABLE,
    LATEST_VIEW,
    ensure_schema,
    extract_patient_ref,
    history_rows,
    insert_version,
    latest_row,
    next_seq,
    version_row,
)


@pytest.fixture()
def connection():
    """A fresh in-memory database with the phase-3 schema and nothing else.

    Deliberately not the session fixture: the log's sequence and row counts are
    the subject here, and the shared connection arrives pre-loaded with the
    fixture bundle.
    """
    con = duckdb.connect()
    ensure_schema(con)
    try:
        yield con
    finally:
        con.close()


def observation(resource_id: str, *, status: str = "final") -> dict:
    return {"resourceType": "Observation", "id": resource_id, "status": status}


def test_schema_creates_the_log_and_the_view(connection):
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name IN (?, ?)",
            [BASE_TABLE, LATEST_VIEW],
        ).fetchall()
    }
    assert tables == {BASE_TABLE, LATEST_VIEW}
    view_type = connection.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = ?", [LATEST_VIEW]
    ).fetchone()[0]
    assert view_type.upper() == "VIEW"


def test_latest_wins_and_history_agree(connection):
    assert next_seq(connection) == 0

    insert_version(connection, resource=observation("o1"), seq=1)
    insert_version(connection, resource=observation("o1", status="amended"), seq=2)

    latest = latest_row(connection, "Observation", "o1")
    assert latest is not None and latest["seq"] == 2
    assert latest["resource"]["status"] == "amended"

    rows = history_rows(connection, "Observation", "o1")
    assert [row["seq"] for row in rows] == [2, 1], "history is newest first"

    assert version_row(connection, "Observation", "o1", 1)["resource"]["status"] == "final"
    assert version_row(connection, "Observation", "o1", 99) is None

    # The view every reader uses keeps exactly one row per (type, id).
    count = connection.execute(f"SELECT count(*) FROM {LATEST_VIEW}").fetchone()[0]
    assert count == 1
    assert next_seq(connection) == 2


def test_tombstone_hides_from_the_view_but_stays_in_history(connection):
    insert_version(connection, resource=observation("o1"), seq=1)
    insert_version(connection, resource=observation("o1"), seq=2, deleted=True)

    assert connection.execute(f"SELECT count(*) FROM {LATEST_VIEW}").fetchone()[0] == 0

    latest = latest_row(connection, "Observation", "o1")
    assert latest is not None and latest["deleted"] is True

    rows = history_rows(connection, "Observation", "o1")
    assert [row["deleted"] for row in rows] == [True, False]

    resource = connection.execute(
        f"SELECT resource FROM {BASE_TABLE} WHERE id = 'o1' ORDER BY _seq"
    ).fetchall()
    assert resource, "the tombstone still carries the last resource body"


def test_legacy_resources_table_is_migrated_into_the_log(connection):
    """A phase-1/2 plain table must keep working (and must not shadow the view)."""
    connection.execute("DROP VIEW IF EXISTS resources")
    connection.execute("DROP TABLE IF EXISTS resources_base")
    connection.execute(
        """
        CREATE TABLE resources (
            id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR
        )
        """
    )
    connection.execute(
        "INSERT INTO resources VALUES ('p1', 'Patient', ?, 'p1')",
        ['{"resourceType": "Patient", "id": "p1"}'],
    )
    connection.execute(
        "INSERT INTO resources VALUES ('o1', 'Observation', ?, 'p1')",
        ['{"resourceType": "Observation", "id": "o1"}'],
    )

    ensure_schema(connection)

    table_type = connection.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = 'resources'"
    ).fetchone()[0]
    assert table_type.upper() == "VIEW"
    assert connection.execute("SELECT count(*) FROM resources").fetchone()[0] == 2
    assert next_seq(connection) == 2

    # The migration is idempotent.
    ensure_schema(connection)
    assert connection.execute("SELECT count(*) FROM resources").fetchone()[0] == 2
    assert next_seq(connection) == 2


def test_patient_reference_follows_the_loader_doctrine():
    assert extract_patient_ref({"resourceType": "Patient", "id": "p1"}) == "p1"
    assert (
        extract_patient_ref(
            {"resourceType": "Observation", "subject": {"reference": "Patient/p1"}}
        )
        == "p1"
    )
    assert (
        extract_patient_ref(
            {
                "resourceType": "Observation",
                "subject": {"reference": "https://example.org/fhir/Patient/p2/_history/3"},
            }
        )
        == "p2"
    )
    # Non-patient subjects, bare ids and urn:uuid-carrying lists follow the
    # 0.0.12 Domain 6 doctrine: never fabricate a phantom patient.
    assert extract_patient_ref(
        {"resourceType": "Observation", "subject": {"reference": "Group/g1"}}
    ) is None
    assert (
        extract_patient_ref({"resourceType": "Observation", "subject": {"reference": "p1"}})
        is None
    )
    assert extract_patient_ref(
        {
            "resourceType": "Appointment",
            "patient": [{"reference": "Group/g1"}, {"reference": "Patient/p3"}],
        }
    ) == "p3"


def test_view_is_readable_when_empty(connection):
    assert connection.execute(f"SELECT count(*) FROM {LATEST_VIEW}").fetchone()[0] == 0
    assert next_seq(connection) == 0
    assert latest_row(connection, "Observation", "absent") is None


def test_migration_survives_a_fresh_memory_database():
    """The migration must not depend on the shared test connection's history."""
    con = duckdb.connect()
    try:
        ensure_schema(con)
        insert_version(con, resource=observation("o1"), seq=1)
        assert con.execute(f"SELECT count(*) FROM {LATEST_VIEW}").fetchone()[0] == 1
    finally:
        con.close()
