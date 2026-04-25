"""
fhir4ds.sources.base
====================
Core contracts for Zero-ETL source adapters.

Defines the SourceAdapter Protocol, SchemaValidationError,
validate_schema(), and quote_identifier() — the shared infrastructure
all adapters depend on.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, runtime_checkable

try:
    from typing import Protocol
except ImportError:  # Python < 3.8 fallback
    from typing_extensions import Protocol  # type: ignore[assignment]


class SchemaValidationError(Exception):
    """
    Raised when a SourceAdapter registers a view that does not conform
    to the required fhir4ds resources schema.

    The message identifies the missing or mistyped column and the adapter
    class that registered the view.
    """


# Required schema: column name -> substring that must appear in the DuckDB type string
_REQUIRED_COLUMNS: dict[str, str] = {
    "id": "VARCHAR",
    "resourceType": "VARCHAR",
    "resource": "JSON",
    "patient_ref": "VARCHAR",
}


def validate_schema(con: Any, adapter_class_name: str) -> None:
    """
    Validates that the ``resources`` view registered by an adapter conforms
    to the required schema.

    Raises :exc:`SchemaValidationError` with a precise message if any column
    is missing or has an incompatible type.  Must be called by every adapter
    immediately after ``CREATE VIEW``.

    Args:
        con: An active DuckDB connection.
        adapter_class_name: The ``__class__.__name__`` of the calling adapter,
            used in error messages.

    Raises:
        SchemaValidationError: If the ``resources`` view is absent, or if a
            required column is missing or has the wrong type.
    """
    try:
        result = con.execute("DESCRIBE resources").fetchall()
    except Exception as exc:
        raise SchemaValidationError(
            f"{adapter_class_name} failed to register a queryable 'resources' view: {exc}"
        ) from exc

    actual_columns: dict[str, str] = {row[0]: row[1].upper() for row in result}

    for col, expected_type in _REQUIRED_COLUMNS.items():
        if col not in actual_columns:
            raise SchemaValidationError(
                f"{adapter_class_name}: required column '{col}' is missing from "
                f"the 'resources' view. "
                f"Actual columns: {list(actual_columns.keys())}"
            )
        actual_type = actual_columns[col]
        if expected_type not in actual_type:
            raise SchemaValidationError(
                f"{adapter_class_name}: column '{col}' has type '{actual_type}' "
                f"but '{expected_type}' is required."
            )


def quote_identifier(name: str) -> str:
    """
    Safely quotes a DuckDB identifier to prevent SQL injection.

    Escapes internal double-quotes by doubling them, then wraps the
    result in double-quotes.

    Args:
        name: The raw identifier string (table name, column name, etc.).

    Returns:
        A quoted identifier string safe for interpolation into SQL.
    """
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


@runtime_checkable
class SourceAdapter(Protocol):
    """
    Protocol defining the interface all fhir4ds source adapters must implement.

    Adapters register an external data source as a DuckDB view named
    ``resources`` that conforms to the fhir4ds schema contract:

    +--------------+---------+------------------------------------------+
    | Column       | Type    | Description                              |
    +==============+=========+==========================================+
    | id           | VARCHAR | FHIR resource ID                         |
    +--------------+---------+------------------------------------------+
    | resourceType | VARCHAR | FHIR resource type (e.g. ``"Patient"``)  |
    +--------------+---------+------------------------------------------+
    | resource     | JSON    | Complete FHIR resource as JSON           |
    +--------------+---------+------------------------------------------+
    | patient_ref  | VARCHAR | Patient ID this resource belongs to      |
    +--------------+---------+------------------------------------------+

    Adapters are responsible for their own connection lifecycle, including
    cleanup on :meth:`unregister`.

    Optional incremental-update interface (Phase 6):
        Adapters may additionally implement :meth:`get_changed_patients` and
        :meth:`supports_incremental` to enable delta evaluation via
        :class:`~fhir4ds.dqm.reactive.ReactiveEvaluator`.
    """

    def register(self, con: Any) -> None:
        """
        Registers the external source as a ``resources`` view in DuckDB.

        Must call :func:`validate_schema` before returning.
        Must be idempotent — safe to call multiple times on the same connection.

        Args:
            con: An active DuckDB connection.

        Raises:
            SchemaValidationError: If the registered view does not conform
                to the required schema.
        """
        ...

    def unregister(self, con: Any) -> None:
        """
        Removes the ``resources`` view and releases any external connections
        created during :meth:`register`.

        Must be safe to call even if :meth:`register` was never called.

        Args:
            con: An active DuckDB connection.
        """
        ...
