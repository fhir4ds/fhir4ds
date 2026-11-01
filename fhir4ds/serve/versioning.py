"""The append-only resource log and its latest-wins view.

Phase 3 makes the surface a FHIR-native writer, so resource storage stops being
"the loader's table" and becomes a versioned log:

* ``resources_base`` — append-only. Every write inserts one row carrying the
  writer-assigned ``_seq`` (a single monotonic integer), a ``_deleted``
  tombstone flag, and ``_ingested_at``. Nothing is ever updated or deleted.
* ``resources`` — a **view** over the base that keeps only the newest version of
  each ``(resourceType, id)`` and drops tombstones. Everything that already
  reads the ``resources`` relation (ViewDefinition generation, the fhirpath
  UDFs, ``$sqlquery-run``) therefore keeps working unchanged, and ``$history``
  reads the base directly.

This module is the *only* place the versioning model is expressed. Reads,
writes and the SQL-on-FHIR path all go through the view; ``_history`` and
vread go through :func:`history_rows`.

A pre-existing plain ``resources`` table (the loader's schema, which phase 1/2
created and ``--resources`` still produces) is migrated into the log on first
boot: its rows are appended with fresh ``_seq`` values in ``id`` order, the
table is dropped, and the view takes its name. That migration is what lets an
old database or a fixture load keep working.
"""

from __future__ import annotations

from typing import Any

#: Physical table: one row per version, append-only.
BASE_TABLE = "resources_base"

#: Logical relation every reader already uses (latest non-deleted version).
LATEST_VIEW = "resources"

#: Columns the ``resources`` relation exposes — the phase-1/2 loader schema.
PUBLIC_COLUMNS: tuple[str, ...] = ("id", "resourceType", "resource", "patient_ref")

_BASE_DDL = f"""
CREATE TABLE IF NOT EXISTS {BASE_TABLE} (
    id VARCHAR,
    resourceType VARCHAR,
    resource JSON,
    patient_ref VARCHAR,
    _seq BIGINT,
    _deleted BOOLEAN DEFAULT FALSE,
    _ingested_at TIMESTAMP
)
"""

_LATEST_DDL = f"""
CREATE OR REPLACE VIEW {LATEST_VIEW} AS
SELECT id, resourceType, resource, patient_ref
FROM (
    SELECT
        id,
        resourceType,
        resource,
        patient_ref,
        _deleted,
        row_number() OVER (PARTITION BY resourceType, id ORDER BY _seq DESC) AS _rn
    FROM {BASE_TABLE}
)
WHERE _rn = 1 AND NOT _deleted
"""

_HISTORY_SQL = f"""
SELECT id, resourceType, resource, patient_ref, _seq, _deleted, _ingested_at
FROM {BASE_TABLE}
WHERE resourceType = ? AND id = ?
ORDER BY _seq DESC
"""

_LATEST_ROW_SQL = f"""
SELECT id, resourceType, resource, patient_ref, _seq, _deleted, _ingested_at
FROM {BASE_TABLE}
WHERE resourceType = ? AND id = ?
ORDER BY _seq DESC
LIMIT 1
"""


def ensure_schema(connection: Any) -> None:
    """Create the log and its view, migrating a legacy ``resources`` table."""
    connection.execute(_BASE_DDL)
    _migrate_legacy_table(connection)
    connection.execute(_LATEST_DDL)


def refresh_view(connection: Any) -> None:
    """Recreate the latest-wins view (idempotent; cheap)."""
    connection.execute(_LATEST_DDL)


def _migrate_legacy_table(connection: Any) -> None:
    """Fold a pre-existing plain ``resources`` table into the log.

    Phase 1/2 created ``resources`` as a table (the loader schema). Leaving it
    in place would shadow the view, so its rows are appended with fresh
    ``_seq`` values and the table is dropped. Idempotent: after the first boot
    ``resources`` is a view, which this function ignores.
    """
    if not _is_table(connection, LATEST_VIEW):
        return
    # Keep the legacy rows, ordered so the migration is deterministic.
    connection.execute(
        f"""
        INSERT INTO {BASE_TABLE}
            (id, resourceType, resource, patient_ref, _seq, _deleted, _ingested_at)
        SELECT
            id,
            resourceType,
            resource,
            patient_ref,
            row_number() OVER (ORDER BY resourceType, id),
            FALSE,
            TIMESTAMP '1970-01-01 00:00:00'
        FROM {LATEST_VIEW}
        """
    )
    connection.execute(f"DROP TABLE {LATEST_VIEW}")


def _is_table(connection: Any, name: str) -> bool:
    """True when ``name`` exists and is a table (not a view)."""
    row = connection.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = ?",
        [name],
    ).fetchone()
    return bool(row) and str(row[0]).upper() == "BASE TABLE"


def next_seq(connection: Any) -> int:
    """Highest committed ``_seq`` in the log (``0`` when empty)."""
    row = connection.execute(f"SELECT max(_seq) FROM {BASE_TABLE}").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def insert_version(
    connection: Any,
    *,
    resource: dict,
    seq: int,
    deleted: bool = False,
) -> None:
    """Append one version row. ``seq`` is assigned by the caller, never here."""
    resource_type = resource.get("resourceType")
    connection.execute(
        f"""
        INSERT INTO {BASE_TABLE}
            (id, resourceType, resource, patient_ref, _seq, _deleted, _ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, now())
        """,
        [
            resource.get("id"),
            resource_type,
            _json_text(resource),
            extract_patient_ref(resource),
            seq,
            deleted,
        ],
    )


def latest_row(
    connection: Any, resource_type: str, resource_id: str
) -> dict[str, Any] | None:
    """Newest version of one resource, including tombstones."""
    row = connection.execute(_LATEST_ROW_SQL, [resource_type, resource_id]).fetchone()
    return _row_to_dict(row) if row else None


def history_rows(
    connection: Any, resource_type: str, resource_id: str
) -> list[dict[str, Any]]:
    """Every version of one resource, newest first."""
    rows = connection.execute(_HISTORY_SQL, [resource_type, resource_id]).fetchall()
    return [_row_to_dict(row) for row in rows]


def version_row(
    connection: Any, resource_type: str, resource_id: str, seq: int
) -> dict[str, Any] | None:
    """One specific version (vread)."""
    row = connection.execute(
        f"SELECT id, resourceType, resource, patient_ref, _seq, _deleted, _ingested_at "
        f"FROM {BASE_TABLE} WHERE resourceType = ? AND id = ? AND _seq = ?",
        [resource_type, resource_id, seq],
    ).fetchone()
    return _row_to_dict(row) if row else None


def _row_to_dict(row: tuple) -> dict[str, Any]:
    import json

    resource_text = row[2]
    resource = json.loads(resource_text) if isinstance(resource_text, str) else resource_text
    return {
        "resource": resource,
        "seq": int(row[4]),
        "deleted": bool(row[5]),
        "ingested_at": row[6],
    }


def _json_text(resource: dict) -> str:
    import json

    return json.dumps(resource, ensure_ascii=False, separators=(",", ":"))


#: Patient identity extraction, mirroring ``FHIRDataLoader._extract_patient_ref``
#: (0.0.12 Domain 6 doctrine): only Patient-typed references attribute a
#: patient. A Group/Location/practitioner subject, a bare id, or a logical
#: reference yields ``None`` so patient-context evaluation can never fabricate
#: a phantom patient from a non-patient subject.
_PATIENT_REF_FIELDS: tuple[str, ...] = ("subject", "patient", "beneficiary")


def extract_patient_ref(resource: dict) -> str | None:
    """Return the patient id a resource belongs to, or ``None``."""
    if resource.get("resourceType") == "Patient":
        return resource.get("id")

    for field in _PATIENT_REF_FIELDS:
        value = resource.get(field)
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            reference = candidate.get("reference")
            if not isinstance(reference, str) or not reference:
                continue
            if reference.startswith("urn:uuid:"):
                return reference[len("urn:uuid:") :]
            if "/" not in reference:
                continue
            segments = [segment for segment in reference.split("/") if segment]
            if len(segments) >= 2 and segments[-2] == "_history":
                segments = segments[:-2]
            if len(segments) >= 2 and segments[-2] == "Patient":
                return segments[-1]
    return None


__all__ = [
    "BASE_TABLE",
    "LATEST_VIEW",
    "PUBLIC_COLUMNS",
    "ensure_schema",
    "refresh_view",
    "next_seq",
    "insert_version",
    "latest_row",
    "history_rows",
    "version_row",
    "extract_patient_ref",
]
