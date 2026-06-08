"""
fhir4ds.sources.filesystem
==========================
SourceAdapter for FHIR resources stored as Parquet, NDJSON, or Iceberg
files on local disk or cloud object storage (S3, Azure Blob, GCS).
"""

from __future__ import annotations

import warnings
from typing import Any

from fhir4ds.sources.base import quote_identifier, quote_sql_literal, validate_schema

_CLOUD_PREFIXES = ("s3://", "az://", "abfs://", "gs://", "gcs://")

_SUPPORTED_FORMATS = ("parquet", "ndjson", "json", "iceberg")

_ALLOWED_SECRET_OPTIONS = {
    "S3": {
        "access_key_id",
        "secret_access_key",
        "session_token",
        "region",
        "endpoint_url",
        "url_style",
        "use_ssl",
    },
    "AZURE": {
        "connection_string",
        "account_name",
        "account_key",
        "tenant_id",
        "client_id",
        "client_secret",
    },
    "GCS": {
        "service_account_json",
    },
}


class CloudCredentials:
    """
    Encapsulates DuckDB secret configuration for cloud storage access.

    Args:
        provider: Cloud provider — ``'S3'``, ``'AZURE'``, or ``'GCS'``.
        secret_name: Optional name for the DuckDB secret.  Defaults to
            ``'fhir4ds_{provider}_secret'``.
        **kwargs: Provider-specific credential fields.

            S3: ``access_key_id``, ``secret_access_key``, ``region``,
            ``endpoint_url``.

            Azure: ``connection_string``, or ``account_name`` +
            ``account_key``.

            GCS: ``service_account_json``.

    Example::

        creds = CloudCredentials(
            provider="S3",
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-east-1",
        )
        source = FileSystemSource("s3://my-bucket/fhir/**/*.parquet", credentials=creds)
    """

    def __init__(
        self,
        provider: str,
        secret_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.provider = provider.upper()
        if self.provider not in _ALLOWED_SECRET_OPTIONS:
            raise ValueError(
                f"Unsupported cloud provider '{provider}'. "
                f"Supported providers: {tuple(_ALLOWED_SECRET_OPTIONS)}"
            )
        self.secret_name = secret_name or f"fhir4ds_{self.provider.lower()}_secret"
        self.kwargs = kwargs

    def configure(self, con: Any) -> None:
        """Registers a DuckDB secret for this provider on *con*."""
        allowed = _ALLOWED_SECRET_OPTIONS[self.provider]
        invalid = sorted(set(self.kwargs) - allowed)
        if invalid:
            raise ValueError(
                f"Unsupported credential option(s) for {self.provider}: {invalid}. "
                f"Supported options: {sorted(allowed)}"
            )

        kv_pairs = ",\n                ".join(
            f"{key} {quote_sql_literal(str(value))}"
            for key, value in self.kwargs.items()
        )
        separator = "," if kv_pairs else ""
        con.execute(f"""
            CREATE OR REPLACE SECRET {quote_identifier(self.secret_name)} (
                TYPE {self.provider}{separator}
                {kv_pairs}
            )
        """)


class FileSystemSource:
    """
    SourceAdapter for FHIR resources stored as Parquet, NDJSON, or
    Iceberg files on local disk or cloud object storage (S3, Azure, GCS).

    The source files must already contain columns conforming to the
    fhir4ds schema: ``id``, ``resourceType``, ``resource``, ``patient_ref``.

    Args:
        path_pattern: Glob pattern or directory path pointing to source
            files.  Examples:

            - ``'/data/fhir/**/*.parquet'``
            - ``'s3://my-bucket/fhir/exports/*.parquet'``
            - ``'/data/fhir/ndjson/'``

        format: File format — ``'parquet'``, ``'ndjson'``, ``'json'``, or
            ``'iceberg'``.  Defaults to ``'parquet'``.
        credentials: Optional :class:`CloudCredentials` for cloud storage
            access.  If ``None`` and *path_pattern* begins with a cloud
            prefix, a :exc:`UserWarning` is emitted that DuckDB secrets
            must be configured externally.
        hive_partitioning: Whether to enable Hive partition pruning.
            Recommended for large Parquet datasets partitioned by
            ``resourceType`` or date.  Defaults to ``False``.

    Raises:
        ValueError: If *format* is not one of the supported values.
        SchemaValidationError: If the mounted files do not conform to
            the required schema.

    Example — local Parquet::

        source = FileSystemSource('/data/fhir/**/*.parquet')
        fhir4ds.attach(con, source)

    Example — S3 with credentials::

        creds = CloudCredentials("S3", access_key_id="...", secret_access_key="...")
        source = FileSystemSource(
            "s3://my-bucket/fhir/**/*.parquet",
            credentials=creds,
            hive_partitioning=True,
        )
        fhir4ds.attach(con, source)
    """

    def __init__(
        self,
        path_pattern: str,
        format: str = "parquet",
        credentials: CloudCredentials | None = None,
        hive_partitioning: bool = False,
    ) -> None:
        if not isinstance(path_pattern, str):
            raise TypeError("path_pattern must be a string")
        if not path_pattern:
            raise ValueError("path_pattern must be non-empty")
        if not isinstance(format, str):
            raise TypeError("format must be a string")
        if not format:
            raise ValueError("format must be non-empty")
        fmt = format.lower()
        if fmt not in _SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{format}'. "
                f"Supported formats: {_SUPPORTED_FORMATS}"
            )
        self._path_pattern = path_pattern
        self._format = fmt
        self._credentials = credentials
        self._hive_partitioning = hive_partitioning
        # Stored during register() for incremental delta scanning
        self._con: Any | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _warn_if_cloud_without_credentials(self) -> None:
        if self._credentials is None:
            for prefix in _CLOUD_PREFIXES:
                if self._path_pattern.startswith(prefix):
                    warnings.warn(
                        f"FileSystemSource path '{self._path_pattern}' appears to be a "
                        f"cloud URI but no credentials were provided. DuckDB secrets must "
                        f"be configured externally before calling register(). "
                        f"Pass a CloudCredentials instance to suppress this warning.",
                        UserWarning,
                        stacklevel=3,
                    )
                    return

    def _build_scan_expression(self) -> str:
        """Builds the DuckDB scan expression for the configured format."""
        # Path is passed to DuckDB's own parser — do not quote as identifier.
        # DuckDB handles glob patterns natively in these functions.
        path_literal = quote_sql_literal(self._path_pattern)
        if self._format == "parquet":
            options = []
            if self._hive_partitioning:
                options.append("hive_partitioning=true")
            opts = f", {', '.join(options)}" if options else ""
            return f"read_parquet({path_literal}{opts})"
        elif self._format in ("ndjson", "json"):
            return f"read_json_auto({path_literal})"
        elif self._format == "iceberg":
            return f"iceberg_scan({path_literal})"
        else:
            raise ValueError(f"Unsupported format: {self._format}")

    def _scan_column_names(self, con: Any, scan_expr: str) -> set[str]:
        """Return the columns exposed by a DuckDB scan expression."""
        rows = con.execute(f"DESCRIBE SELECT * FROM {scan_expr}").fetchall()
        return {row[0] for row in rows}

    def _raw_fhir_patient_ref_sql(self, resource_expr: str) -> str:
        """Build SQL that derives patient_ref from a raw FHIR resource JSON."""
        reference_expr = (
            f"COALESCE("
            f"json_extract_string({resource_expr}, '$.subject.reference'), "
            f"json_extract_string({resource_expr}, '$.patient.reference'), "
            f"json_extract_string({resource_expr}, '$.beneficiary.reference')"
            f")"
        )
        normalized_ref = (
            f"regexp_replace("
            f"regexp_replace({reference_expr}, '^urn:uuid:', ''), "
            f"'^.*/', ''"
            f")"
        )
        return (
            f"CASE "
            f"WHEN src.resourceType = 'Patient' THEN src.id::VARCHAR "
            f"ELSE {normalized_ref} "
            f"END"
        )

    def _resources_view_sql(self, con: Any, scan_expr: str) -> str:
        """Build the CREATE VIEW statement for the configured file source."""
        columns = self._scan_column_names(con, scan_expr)
        has_resources_schema = {
            "id",
            "resourceType",
            "resource",
            "patient_ref",
        }.issubset(columns)

        if has_resources_schema:
            # Qualify source columns with src.* so a missing input column cannot
            # be confused with a SELECT-list alias of the same name.
            return f"""
                CREATE OR REPLACE VIEW resources AS
                SELECT
                    src.id::VARCHAR           AS id,
                    src.resourceType::VARCHAR AS resourceType,
                    src.resource::JSON        AS resource,
                    src.patient_ref::VARCHAR  AS patient_ref
                FROM {scan_expr} AS src
            """

        if self._format in ("ndjson", "json") and {"id", "resourceType"}.issubset(columns):
            resource_expr = "to_json(src)"
            return f"""
                CREATE OR REPLACE VIEW resources AS
                SELECT
                    src.id::VARCHAR           AS id,
                    src.resourceType::VARCHAR AS resourceType,
                    {resource_expr}::JSON     AS resource,
                    {self._raw_fhir_patient_ref_sql(resource_expr)}::VARCHAR AS patient_ref
                FROM {scan_expr} AS src
            """

        return f"""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                src.id::VARCHAR           AS id,
                src.resourceType::VARCHAR AS resourceType,
                src.resource::JSON        AS resource,
                src.patient_ref::VARCHAR  AS patient_ref
            FROM {scan_expr} AS src
        """

    # ------------------------------------------------------------------
    # SourceAdapter interface
    # ------------------------------------------------------------------

    def register(self, con: Any) -> None:
        """
        Mounts the file source as the ``resources`` view.

        Configures cloud credentials (if provided), builds the DuckDB
        scan expression, creates the view, then validates the schema.

        Raises:
            SchemaValidationError: If the files do not expose the required
                columns with the required types.
        """
        from fhir4ds.sources.base import SchemaValidationError

        self._warn_if_cloud_without_credentials()

        if self._credentials is not None:
            self._credentials.configure(con)

        scan_expr = self._build_scan_expression()
        try:
            # Explicit casts ensure portable JSON type regardless of whether
            # the source is Parquet, NDJSON (STRUCT), or already-typed JSON.
            con.execute(self._resources_view_sql(con, scan_expr))
        except Exception as exc:
            raise SchemaValidationError(
                f"{self.__class__.__name__} failed to create the 'resources' view: {exc}"
            ) from exc

        self._con = con
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
        self._con = None

    def supports_incremental(self) -> bool:
        """
        Returns ``True`` for Parquet, NDJSON, and JSON formats.

        Iceberg format does not support file-mtime-based delta tracking.
        """
        return self._format in ("parquet", "ndjson", "json")

    def get_changed_patients(self, since: datetime) -> list[str]:  # type: ignore[name-defined]  # noqa: F821
        """
        Returns patients whose source files have been modified since *since*
        by scanning file modification timestamps.

        Limitations:

        - File mtime is not a reliable proxy for patient-level data changes.
          A file touched without data changes will produce false positives.
        - Deletions within a file are not detectable — only file-level changes.
        - Cloud storage mtime may have lower resolution than local filesystem.
        - Only supported for Parquet, NDJSON, and JSON formats.

        Args:
            since: UTC :class:`datetime` timestamp.  Only files modified
                strictly after this time are scanned.

        Returns:
            List of distinct ``patient_ref`` values from modified files.
            Empty list if no files have changed.

        Raises:
            NotImplementedError: If the adapter format does not support
                incremental updates (e.g. ``'iceberg'``).
            RuntimeError: If called before :meth:`register`.
        """
        import glob as glob_module
        import os
        from datetime import datetime

        if not self.supports_incremental():
            raise NotImplementedError(
                f"Incremental updates are not supported for format '{self._format}'."
            )

        if self._con is None:
            raise RuntimeError(
                "Cannot call get_changed_patients() before register()."
            )

        changed_files = [
            f
            for f in glob_module.glob(self._path_pattern, recursive=True)
            if datetime.utcfromtimestamp(os.path.getmtime(f)) > since
        ]

        if not changed_files:
            return []

        if self._format == "parquet":
            paths = ", ".join(quote_sql_literal(path) for path in changed_files)
            scan = f"read_parquet([{paths}])"
        else:
            paths = ", ".join(quote_sql_literal(path) for path in changed_files)
            scan = f"read_json_auto([{paths}])"

        rows = self._con.execute(f"""
            SELECT DISTINCT patient_ref FROM {scan}
        """).fetchall()

        return [row[0] for row in rows if row[0] is not None]
