"""field_values index store (DuckDB).

AMUX-150 chunk B: the store is entity-typed. ``field_values`` carries an
``entity_type`` column (default ``'Patient'``); the exact index is
``(entity_type, field_name, value)``. Patient tables, Linkage pair keys,
and ``patient_membership`` are untouched — existing databases are migrated
in place (``ALTER TABLE ... ADD COLUMN`` + backfill) and patient queries
keep their exact behavior.
"""

from __future__ import annotations

import re

import duckdb

from .normalizers import extract_patient_fields

__all__ = [
    "create_matching_tables",
    "index_patient",
    "index_entity",
    "exact_candidates",
    "FIELD_VALUES_DDL",
]

FIELD_VALUES_DDL = """
CREATE TABLE IF NOT EXISTS field_values (
    patient_id VARCHAR,
    field_name VARCHAR,
    value VARCHAR,
    entity_type VARCHAR DEFAULT 'Patient'
)
"""

_INDEX_DDL = "CREATE INDEX IF NOT EXISTS idx_field_values_field_value ON field_values (field_name, value)"

_ENTITY_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_field_values_entity_field_value "
    "ON field_values (entity_type, field_name, value)"
)

# FHIR R4 id pattern (same doctrine as FHIRDataLoader): also protects the
# "|" pair-key used by the linkage table from separator injection.
_FHIR_ID_RE = re.compile(r"^[A-Za-z0-9-.]{1,64}$")


def create_matching_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(FIELD_VALUES_DDL)
    # In-place migration for pre-AMUX-150 databases (single-column schema).
    columns = {
        row[0] for row in conn.execute(
            "SELECT column_name FROM duckdb_columns() "
            "WHERE table_name = 'field_values'").fetchall()
    }
    if "entity_type" not in columns:
        conn.execute(
            "ALTER TABLE field_values ADD COLUMN entity_type VARCHAR "
            "DEFAULT 'Patient'")
        conn.execute(
            "UPDATE field_values SET entity_type = 'Patient' "
            "WHERE entity_type IS NULL")
    conn.execute(_INDEX_DDL)
    conn.execute(_ENTITY_INDEX_DDL)


def index_entity(
    conn: duckdb.DuckDBPyConnection,
    entity_type: str,
    resource: dict,
    fields: dict[str, list[str]],
) -> int:
    """Insert one entity's PRE-EXTRACTED normalized field values.

    The caller supplies the per-type extractor's output (AMUX-150 §3.2);
    id validation mirrors :func:`index_patient`. Idempotent: deletes any
    prior rows for (entity_type, id) first. Returns rows inserted.
    """
    if not isinstance(entity_type, str) or not entity_type:
        raise ValueError("entity_type must be a non-empty string")
    if not isinstance(resource, dict):
        raise TypeError(
            f"resource must be a dict, got {type(resource).__name__}")
    entity_id = resource.get("id")
    if not isinstance(entity_id, str) or not entity_id:
        raise ValueError("resource must carry a non-empty string 'id'")
    if not _FHIR_ID_RE.fullmatch(entity_id):
        raise ValueError(
            f"Entity id {entity_id!r} does not match the FHIR id pattern "
            "^[A-Za-z0-9-.]{1,64}$"
        )
    create_matching_tables(conn)
    conn.execute(
        "DELETE FROM field_values WHERE entity_type = ? AND patient_id = ?",
        [entity_type, entity_id])
    rows = [(entity_id, name, value, entity_type)
            for name, values in fields.items() for value in values]
    if rows:
        conn.executemany("INSERT INTO field_values VALUES (?, ?, ?, ?)", rows)
    return len(rows)


def index_patient(conn: duckdb.DuckDBPyConnection, patient_resource: dict) -> int:
    """Extract + insert a patient's normalized field values.

    Idempotent: deletes any prior rows for the patient_id first.
    Returns the number of rows inserted.
    """
    if not isinstance(patient_resource, dict):
        raise TypeError(
            f"patient_resource must be a dict (a FHIR Patient resource), "
            f"got {type(patient_resource).__name__}"
        )
    patient_id = patient_resource.get("id")
    if not isinstance(patient_id, str) or not patient_id:
        raise ValueError("Patient resource must carry a non-empty string 'id'")
    if not _FHIR_ID_RE.fullmatch(patient_id):
        raise ValueError(
            f"Patient id {patient_id!r} does not match the FHIR id pattern "
            "^[A-Za-z0-9-.]{1,64}$"
        )
    return index_entity(
        conn, "Patient", patient_resource,
        extract_patient_fields(patient_resource))


def exact_candidates(
    conn: duckdb.DuckDBPyConnection,
    field_name: str,
    value: str,
    entity_type: str = "Patient",
) -> list[str]:
    """Distinct entity ids having an exact (field_name, value) row, sorted."""
    result = conn.execute(
        "SELECT DISTINCT patient_id FROM field_values "
        "WHERE entity_type = ? AND field_name = ? AND value = ? "
        "ORDER BY patient_id",
        [entity_type, field_name, value],
    ).fetchall()
    return [r[0] for r in result]
