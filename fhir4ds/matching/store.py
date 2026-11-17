"""field_values index store (DuckDB)."""

from __future__ import annotations

import re

import duckdb

from .normalizers import extract_patient_fields

__all__ = ["create_matching_tables", "index_patient", "exact_candidates", "FIELD_VALUES_DDL"]

FIELD_VALUES_DDL = """
CREATE TABLE IF NOT EXISTS field_values (
    patient_id VARCHAR,
    field_name VARCHAR,
    value VARCHAR
)
"""

_INDEX_DDL = "CREATE INDEX IF NOT EXISTS idx_field_values_field_value ON field_values (field_name, value)"

# FHIR R4 id pattern (same doctrine as FHIRDataLoader): also protects the
# "|" pair-key used by the linkage table from separator injection.
_FHIR_ID_RE = re.compile(r"^[A-Za-z0-9-.]{1,64}$")


def create_matching_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(FIELD_VALUES_DDL)
    conn.execute(_INDEX_DDL)


def index_patient(conn: duckdb.DuckDBPyConnection, patient_resource: dict) -> int:
    """Extract + insert a patient's normalized field values.

    Idempotent: deletes any prior rows for the patient_id first.
    Returns the number of rows inserted.
    """
    patient_id = patient_resource.get("id")
    if not isinstance(patient_id, str) or not patient_id:
        raise ValueError("Patient resource must carry a non-empty string 'id'")
    if not _FHIR_ID_RE.fullmatch(patient_id):
        raise ValueError(
            f"Patient id {patient_id!r} does not match the FHIR id pattern "
            "^[A-Za-z0-9-.]{1,64}$"
        )
    fields = extract_patient_fields(patient_resource)
    conn.execute("DELETE FROM field_values WHERE patient_id = ?", [patient_id])
    rows = [(patient_id, name, value) for name, values in fields.items() for value in values]
    if rows:
        conn.executemany("INSERT INTO field_values VALUES (?, ?, ?)", rows)
    return len(rows)


def exact_candidates(conn: duckdb.DuckDBPyConnection, field_name: str, value: str) -> list[str]:
    """Distinct patient ids having an exact (field_name, value) row, sorted."""
    result = conn.execute(
        "SELECT DISTINCT patient_id FROM field_values WHERE field_name = ? AND value = ? ORDER BY patient_id",
        [field_name, value],
    ).fetchall()
    return [r[0] for r in result]
