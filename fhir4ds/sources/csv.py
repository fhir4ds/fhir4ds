"""
fhir4ds.sources.csv
===================
SourceAdapter for FHIR resources stored in CSV files, where the user
defines a SQL projection mapping their column layout to the fhir4ds schema.

This adapter is intentionally simple — it does not attempt to construct
FHIR JSON automatically.  Users provide the projection SQL, giving them
full control over how their flat data maps to the resources schema.
"""

from __future__ import annotations

from typing import Any

from fhir4ds.sources.base import SchemaValidationError, validate_schema


class CSVSource:
    """
    SourceAdapter for FHIR resources stored in CSV files, where the user
    defines a SQL projection mapping their column layout to the fhir4ds schema.

    The *projection_sql* must be a ``SELECT`` statement that reads from the
    ``{source}`` placeholder and produces exactly the columns:
    ``id`` (VARCHAR), ``resourceType`` (VARCHAR), ``resource`` (JSON),
    ``patient_ref`` (VARCHAR).

    Args:
        path: Path to the CSV file or glob pattern.
        projection_sql: A SQL ``SELECT`` statement projecting the CSV columns
            to the fhir4ds schema.  Use the placeholder ``{source}`` in your
            ``FROM`` clause — it will be replaced with the correct DuckDB scan
            expression ``read_csv_auto('<path>')``.

    Raises:
        SchemaValidationError: If the projection does not produce the required
            columns with the required types.

    Example::

        source = CSVSource(
            path='/data/patients.csv',
            projection_sql=\\\"\\\"\\\"
                SELECT
                    patient_id AS id,
                    'Patient'  AS resourceType,
                    json_object(
                        'resourceType', 'Patient',
                        'id', patient_id,
                        'birthDate', birth_date,
                        'gender', gender
                    ) AS resource,
                    patient_id AS patient_ref
                FROM {source}
            \\\"\\\"\\\"
        )
        fhir4ds.attach(con, source)
    """

    def __init__(self, path: str, projection_sql: str) -> None:
        self._path = path
        self._projection_sql = projection_sql

    # ------------------------------------------------------------------
    # SourceAdapter interface
    # ------------------------------------------------------------------

    def register(self, con: Any) -> None:
        """
        Creates the ``resources`` view from the user-supplied projection.

        Substitutes the ``{source}`` placeholder with
        ``read_csv_auto('<path>')`` then runs ``CREATE OR REPLACE VIEW``
        and validates the schema.

        Raises:
            SchemaValidationError: If the projection does not expose the
                required columns with the required types, or if the view
                cannot be created (e.g. projection references non-existent
                columns).
        """
        scan_expr = f"read_csv_auto('{self._path}')"
        projection = self._projection_sql.replace("{source}", scan_expr)
        try:
            con.execute(f"CREATE OR REPLACE VIEW resources AS {projection}")
        except Exception as exc:
            raise SchemaValidationError(
                f"{self.__class__.__name__} failed to create the 'resources' view: {exc}"
            ) from exc
        validate_schema(con, self.__class__.__name__)

    def unregister(self, con: Any) -> None:
        """
        Drops the ``resources`` view.

        Safe to call even if :meth:`register` was never called.
        """
        try:
            con.execute("DROP VIEW IF EXISTS resources")
        except Exception:
            pass

    def supports_incremental(self) -> bool:
        """CSVSource does not support incremental delta tracking."""
        return False
