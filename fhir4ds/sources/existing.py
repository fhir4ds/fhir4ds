"""
fhir4ds.sources.existing
========================
SourceAdapter for connections that already have a ``resources`` table or
view loaded via :class:`~fhir4ds.cql.loader.FHIRDataLoader` or any other
mechanism.

This adapter is the reference implementation for all other adapters and
ensures full API uniformity — existing users can wrap their pre-loaded
data in the same ``attach()``/``detach()`` API without changing their
workflow.
"""

from __future__ import annotations

from typing import Any

from fhir4ds.sources.base import SchemaValidationError, quote_identifier, validate_schema


class ExistingTableSource:
    """
    SourceAdapter for connections that already have a ``resources`` table
    or view loaded via :class:`~fhir4ds.cql.loader.FHIRDataLoader` or any
    other mechanism.

    Creates a view over the existing table to conform to the
    :class:`~fhir4ds.sources.base.SourceAdapter` interface without
    duplicating data.  When *table_name* is already ``"resources"``, the
    view is a transparent pass-through that still enforces schema validation.

    Args:
        table_name: Name of the existing DuckDB table or view containing
            FHIR resources.  Defaults to ``"resources"``.

    Raises:
        SchemaValidationError: If the existing table does not conform to
            the required schema.

    Example — wrapping a pre-loaded table::

        loader = FHIRDataLoader(con)
        loader.load_directory('/data/fhir/')

        source = ExistingTableSource()          # wraps the default 'resources' table
        fhir4ds.attach(con, source)             # validates schema immediately

    Example — wrapping a custom table name::

        source = ExistingTableSource("my_fhir_table")
        fhir4ds.attach(con, source)             # creates a 'resources' view over 'my_fhir_table'
    """

    def __init__(self, table_name: str = "resources") -> None:
        self._table_name = table_name
        self._created_view: bool = False

    # ------------------------------------------------------------------
    # SourceAdapter interface
    # ------------------------------------------------------------------

    def register(self, con: Any) -> None:
        """
        Validates (and optionally creates) the ``resources`` view.

        When *table_name* differs from ``"resources"``, creates a
        ``CREATE OR REPLACE VIEW resources`` projection.  When
        *table_name* is already ``"resources"``, skips view creation and
        runs schema validation directly on the existing table/view.

        Raises:
            SchemaValidationError: If the table/view is missing required
                columns or has incompatible column types.
        """
        if self._table_name != "resources":
            quoted = quote_identifier(self._table_name)
            con.execute(f"""
                CREATE OR REPLACE VIEW resources AS
                SELECT id, resourceType, resource, patient_ref
                FROM {quoted}
            """)
            self._created_view = True

        validate_schema(con, self.__class__.__name__)

    def unregister(self, con: Any) -> None:
        """
        Drops the ``resources`` view if it was created by this adapter.

        Safe to call even if :meth:`register` was never called or if the
        view was already dropped.
        """
        if self._created_view:
            try:
                con.execute("DROP VIEW IF EXISTS resources")
            except Exception:
                pass
            self._created_view = False

    def supports_incremental(self) -> bool:
        """ExistingTableSource does not support incremental delta tracking."""
        return False
