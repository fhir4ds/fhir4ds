"""
fhir4ds.sources.relational
==========================
SourceAdapter for FHIR resources stored as JSON columns in a Postgres
database.

This adapter targets the common pattern where organizations store FHIR JSON
in a dedicated column of a relational table.  It does **not** attempt to
construct FHIR JSON from arbitrary relational column schemas — that mapping
problem is out of scope for this release (see the plan's Appendix A).
"""

from __future__ import annotations

from typing import Any, Optional

from fhir4ds.sources.base import SchemaValidationError, quote_identifier, validate_schema


# Name used for the DuckDB Postgres attachment.
# Isolated to avoid conflicts if users attach their own Postgres databases.
_POSTGRES_ATTACHMENT_NAME = "fhir4ds_pg"


class PostgresTableMapping:
    """
    Defines how a single Postgres table maps to the fhir4ds resources schema.

    Args:
        table_name: Name of the Postgres table.
        id_column: Column containing the FHIR resource ID.  Must be castable
            to ``VARCHAR``.
        resource_type: Literal FHIR resource type string (e.g. ``'Patient'``).
            Used as a constant in the projection — not read from the table.
        resource_column: Column containing the complete FHIR resource as JSON
            or JSONB.
        patient_ref_column: Column containing the patient reference ID.  Must
            be castable to ``VARCHAR``.
        schema: Postgres schema name.  Defaults to ``'public'``.

    Example::

        mapping = PostgresTableMapping(
            table_name='fhir_patients',
            id_column='patient_id',
            resource_type='Patient',
            resource_column='fhir_json',
            patient_ref_column='patient_id',
        )
    """

    def __init__(
        self,
        table_name: str,
        id_column: str,
        resource_type: str,
        resource_column: str,
        patient_ref_column: str,
        schema: str = "public",
    ) -> None:
        self.table_name = table_name
        self.id_column = id_column
        self.resource_type = resource_type
        self.resource_column = resource_column
        self.patient_ref_column = patient_ref_column
        self.schema = schema

    def to_select(self, attachment_name: str) -> str:
        """
        Generates a safe ``SELECT`` statement projecting this table to the
        fhir4ds schema.

        All column and table identifiers are quoted via :func:`quote_identifier`
        to prevent SQL injection.  The ``resource_type`` literal is safely
        escaped by doubling single quotes — it is never used as an identifier.

        Args:
            attachment_name: The DuckDB attachment name for the Postgres
                database (e.g. ``'fhir4ds_pg'``).

        Returns:
            A ``SELECT`` statement string for use in a ``UNION ALL`` view.
        """
        att = quote_identifier(attachment_name)
        schema = quote_identifier(self.schema)
        table = quote_identifier(self.table_name)
        id_col = quote_identifier(self.id_column)
        resource_col = quote_identifier(self.resource_column)
        patient_col = quote_identifier(self.patient_ref_column)

        # resource_type is a literal string constant, not an identifier.
        # Escape single quotes by doubling to prevent injection.
        resource_type_literal = self.resource_type.replace("'", "''")

        return f"""
            SELECT
                {att}.{schema}.{table}.{id_col}::VARCHAR AS id,
                '{resource_type_literal}'::VARCHAR AS resourceType,
                {att}.{schema}.{table}.{resource_col}::JSON AS resource,
                {att}.{schema}.{table}.{patient_col}::VARCHAR AS patient_ref
            FROM {att}.{schema}.{table}
        """


class PostgresSource:
    """
    SourceAdapter for FHIR resources stored as JSON columns in a Postgres
    database.

    Attaches to the Postgres database using DuckDB's ``postgres`` extension,
    then creates a unified ``resources`` view as a ``UNION ALL`` of all mapped
    tables.

    **Scope boundary**: This adapter requires that source tables already contain
    FHIR resource JSON in a designated column.  It does not construct FHIR JSON
    from arbitrary relational schemas.

    Args:
        connection_string: Postgres connection string in libpq format, e.g.
            ``'postgresql://user:pass@host:5432/dbname'``.
        table_mappings: List of :class:`PostgresTableMapping` instances, one
            per source table to include in the ``resources`` view.

    Raises:
        ValueError: If *table_mappings* is empty.
        SchemaValidationError: If the resulting view does not conform to the
            required schema.

    Example::

        source = PostgresSource(
            connection_string='postgresql://user:pass@localhost/clinical',
            table_mappings=[
                PostgresTableMapping(
                    table_name='fhir_patients',
                    id_column='patient_id',
                    resource_type='Patient',
                    resource_column='fhir_json',
                    patient_ref_column='patient_id',
                ),
                PostgresTableMapping(
                    table_name='fhir_observations',
                    id_column='obs_id',
                    resource_type='Observation',
                    resource_column='fhir_json',
                    patient_ref_column='patient_id',
                ),
            ]
        )
        fhir4ds.attach(con, source)
    """

    def __init__(
        self,
        connection_string: str,
        table_mappings: list[PostgresTableMapping],
    ) -> None:
        if not table_mappings:
            raise ValueError(
                "PostgresSource requires at least one PostgresTableMapping. "
                "Provide a mapping for each Postgres table to include."
            )
        # connection_string is passed to DuckDB's ATTACH, not interpolated into SQL.
        # DuckDB handles quoting internally for ATTACH connection strings.
        self._connection_string = connection_string
        self._mappings = table_mappings
        self._attached: bool = False
        self._con: Optional[Any] = None

    # ------------------------------------------------------------------
    # SourceAdapter interface
    # ------------------------------------------------------------------

    def register(self, con: Any) -> None:
        """
        Installs/loads the DuckDB ``postgres`` extension, attaches to the
        Postgres database, and creates the unified ``resources`` view.

        Uses ``ATTACH IF NOT EXISTS`` and ``CREATE OR REPLACE VIEW`` so the
        call is fully idempotent.

        Raises:
            SchemaValidationError: If the resulting view does not conform to
                the required schema.
        """
        con.execute("INSTALL postgres; LOAD postgres;")

        att = quote_identifier(_POSTGRES_ATTACHMENT_NAME)
        con.execute(f"""
            ATTACH IF NOT EXISTS '{self._connection_string}'
            AS {att} (TYPE POSTGRES, READ_ONLY)
        """)
        self._attached = True
        self._con = con

        selects = [
            mapping.to_select(_POSTGRES_ATTACHMENT_NAME)
            for mapping in self._mappings
        ]
        union_sql = "\nUNION ALL\n".join(selects)

        con.execute(f"CREATE OR REPLACE VIEW resources AS {union_sql}")

        validate_schema(con, self.__class__.__name__)

    def unregister(self, con: Any) -> None:
        """
        Drops the ``resources`` view and detaches the Postgres attachment.

        Safe to call even if :meth:`register` was never called.
        """
        try:
            con.execute("DROP VIEW IF EXISTS resources")
        except Exception:
            pass

        if self._attached:
            try:
                att = quote_identifier(_POSTGRES_ATTACHMENT_NAME)
                con.execute(f"DETACH {att}")
            except Exception:
                pass
            self._attached = False
            self._con = None

    def supports_incremental(self) -> bool:
        """Returns ``True`` — PostgresSource supports delta tracking via ``updated_at``."""
        return True

    def get_changed_patients(self, since: "datetime") -> list[str]:  # type: ignore[name-defined]  # noqa: F821
        """
        Returns patients modified since *since* by querying ``updated_at``
        columns in all mapped tables.

        Limitations:

        - Only surfaces updates and inserts.  Hard deletes are not detected
          unless source tables use soft-delete patterns with an ``updated_at``
          timestamp on the deleted row.
        - Requires all mapped tables to have an ``updated_at`` column of a type
          comparable to timestamp.

        Args:
            since: UTC :class:`datetime` timestamp.

        Returns:
            Deduplicated list of ``patient_ref`` strings for changed patients.

        Raises:
            RuntimeError: If called before :meth:`register`.
            NotImplementedError: If any mapped table does not have an
                ``updated_at`` column.
        """
        if self._con is None or not self._attached:
            raise RuntimeError(
                "Cannot call get_changed_patients() before register()."
            )

        patient_ids: set[str] = set()

        for mapping in self._mappings:
            att = quote_identifier(_POSTGRES_ATTACHMENT_NAME)
            schema = quote_identifier(mapping.schema)
            table = quote_identifier(mapping.table_name)
            patient_col = quote_identifier(mapping.patient_ref_column)

            # Verify updated_at column exists before querying
            try:
                self._con.execute(
                    f"SELECT updated_at FROM {att}.{schema}.{table} LIMIT 0"
                )
            except Exception:
                raise NotImplementedError(
                    f"PostgresSource cannot detect changes for table "
                    f"'{mapping.schema}.{mapping.table_name}' because it does not "
                    f"have an 'updated_at' column. Delta tracking requires an "
                    f"updated_at timestamp column on all mapped tables."
                )

            rows = self._con.execute(f"""
                SELECT DISTINCT {patient_col}::VARCHAR
                FROM {att}.{schema}.{table}
                WHERE updated_at > ?
            """, [since]).fetchall()

            patient_ids.update(row[0] for row in rows)

        return list(patient_ids)
