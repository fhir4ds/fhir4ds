"""
fhir4ds.sources.hapi_postgres
=============================
SourceAdapter for HAPI FHIR JPA Server databases backed by PostgreSQL.

This adapter reads current FHIR resources in place through DuckDB's Postgres
extension. It targets the HAPI JPA storage layout where ``hfj_resource`` holds
the current resource metadata and ``hfj_res_ver`` holds serialized resource
versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fhir4ds.sources.base import (
    quote_identifier,
    quote_sql_literal,
    validate_schema,
)

_HAPI_POSTGRES_ATTACHMENT_NAME = "fhir4ds_hapi_pg"
_DEFAULT_PATIENT_REFERENCE_PATHS = (
    "$.subject.reference",
    "$.patient.reference",
    "$.beneficiary.reference",
)


@dataclass(frozen=True)
class HapiPostgresSchema:
    """
    Configurable HAPI JPA schema mapping.

    Defaults match the current HAPI 8.8 PostgreSQL schema observed in the
    official ``hapiproject/hapi`` container. Override table or column names for
    older HAPI versions or local schema customizations.
    """

    schema: str = "public"
    resource_table: str = "hfj_resource"
    version_table: str = "hfj_res_ver"
    resource_pk_column: str = "res_id"
    version_resource_fk_column: str = "res_id"
    resource_type_column: str = "res_type"
    fhir_id_column: str = "fhir_id"
    current_version_column: str = "res_ver"
    version_number_column: str = "res_ver"
    updated_at_column: str = "res_updated"
    deleted_at_column: str = "res_deleted_at"
    encoding_column: str = "res_encoding"
    text_vc_column: str = "res_text_vc"


class HapiPostgresSource:
    """
    SourceAdapter for a HAPI FHIR JPA Server PostgreSQL backend.

    The adapter creates the standard FHIR4DS ``resources`` view from HAPI's
    current-resource metadata and version-content tables. V1 supports current,
    non-deleted resources stored inline as JSON in ``res_text_vc`` with
    ``res_encoding = 'JSON'``. Compressed ``JSONC``/LOB rows are detected and
    rejected by default so analysis does not silently omit resources.
    """

    def __init__(
        self,
        connection_string: str,
        *,
        schema: HapiPostgresSchema | None = None,
        attachment_name: str = _HAPI_POSTGRES_ATTACHMENT_NAME,
        fail_on_unsupported_storage: bool = True,
        patient_reference_paths: tuple[str, ...] = _DEFAULT_PATIENT_REFERENCE_PATHS,
    ) -> None:
        self._connection_string = connection_string
        self._schema = schema or HapiPostgresSchema()
        self._attachment_name = attachment_name
        self._fail_on_unsupported_storage = fail_on_unsupported_storage
        self._patient_reference_paths = patient_reference_paths
        self._attached = False
        self._con: Any | None = None

    def register(self, con: Any) -> None:
        """
        Attach the HAPI PostgreSQL database and create the ``resources`` view.
        """
        con.execute("INSTALL postgres; LOAD postgres;")

        att = quote_identifier(self._attachment_name)
        con.execute(f"""
            ATTACH IF NOT EXISTS {quote_sql_literal(self._connection_string)}
            AS {att} (TYPE POSTGRES, READ_ONLY)
        """)
        self._attached = True
        self._con = con

        if self._fail_on_unsupported_storage:
            unsupported = self._unsupported_storage_count(con)
            if unsupported:
                raise NotImplementedError(
                    "HapiPostgresSource v1 supports only current resources stored "
                    f"inline as JSON in {self._schema.version_table}."
                    f"{self._schema.text_vc_column}; found {unsupported} current "
                    "resource version(s) using compressed/LOB or non-JSON storage. "
                    "Set fail_on_unsupported_storage=False to skip them explicitly."
                )

        con.execute(
            f"CREATE OR REPLACE VIEW resources AS {self._current_resources_select()}"
        )
        validate_schema(con, self.__class__.__name__)

    def unregister(self, con: Any) -> None:
        """Drop the ``resources`` view and detach the Postgres database."""
        try:
            con.execute("DROP VIEW IF EXISTS resources")
        except Exception:
            pass

        if self._attached:
            try:
                con.execute(f"DETACH {quote_identifier(self._attachment_name)}")
            except Exception:
                pass
            self._attached = False
            self._con = None

    def supports_incremental(self) -> bool:
        """
        Return ``True`` for insert/update delta checks on current resources.

        Deletes and compressed resource bodies are outside the v1 incremental
        scope because patient attribution may require historical resource body
        decoding.
        """
        return True

    def get_changed_patients(self, since: datetime) -> list[str]:
        """
        Return patient IDs for current inline-JSON resources updated after *since*.
        """
        if self._con is None or not self._attached:
            raise RuntimeError(
                "Cannot call get_changed_patients() before register()."
            )

        rows = self._con.execute(f"""
            SELECT DISTINCT patient_ref
            FROM ({self._current_resources_select(include_updated_at=True)}) hapi_resources
            WHERE updated_at > ?
              AND patient_ref IS NOT NULL
        """, [since]).fetchall()
        return sorted({row[0] for row in rows if row[0] is not None})

    def _unsupported_storage_count(self, con: Any) -> int:
        row = con.execute(f"""
            SELECT count(*)::BIGINT
            FROM {self._resource_relation()} r
            JOIN {self._version_relation()} v
              ON v.{self._version_resource_fk()} = r.{self._resource_pk()}
             AND v.{self._version_number()} = r.{self._current_version()}
            WHERE r.{self._deleted_at()} IS NULL
              AND (
                v.{self._encoding()} <> 'JSON'
                OR v.{self._text_vc()} IS NULL
              )
        """).fetchone()
        return int(row[0] or 0)

    def _current_resources_select(self, *, include_updated_at: bool = False) -> str:
        updated_at_projection = (
            f",\n                r.{self._updated_at()} AS updated_at"
            if include_updated_at
            else ""
        )
        return f"""
            SELECT
                r.{self._fhir_id()}::VARCHAR AS id,
                r.{self._resource_type()}::VARCHAR AS resourceType,
                v.{self._text_vc()}::JSON AS resource,
                {self._patient_ref_expression()}::VARCHAR AS patient_ref
                {updated_at_projection}
            FROM {self._resource_relation()} r
            JOIN {self._version_relation()} v
              ON v.{self._version_resource_fk()} = r.{self._resource_pk()}
             AND v.{self._version_number()} = r.{self._current_version()}
            WHERE r.{self._deleted_at()} IS NULL
              AND v.{self._encoding()} = 'JSON'
              AND v.{self._text_vc()} IS NOT NULL
        """

    def _patient_ref_expression(self) -> str:
        resource_type = f"r.{self._resource_type()}"
        fhir_id = f"r.{self._fhir_id()}"
        resource_json = f"v.{self._text_vc()}::JSON"
        candidates = [
            f"CASE WHEN {resource_type} = 'Patient' THEN {fhir_id}::VARCHAR END"
        ]
        for path in self._patient_reference_paths:
            path_literal = quote_sql_literal(path)
            candidates.append(
                "NULLIF(regexp_extract("
                f"json_extract_string({resource_json}, {path_literal}), "
                "'^Patient/(.+)$', 1), '')"
            )
        return f"COALESCE({', '.join(candidates)})"

    def _resource_relation(self) -> str:
        return (
            f"{quote_identifier(self._attachment_name)}."
            f"{quote_identifier(self._schema.schema)}."
            f"{quote_identifier(self._schema.resource_table)}"
        )

    def _version_relation(self) -> str:
        return (
            f"{quote_identifier(self._attachment_name)}."
            f"{quote_identifier(self._schema.schema)}."
            f"{quote_identifier(self._schema.version_table)}"
        )

    def _resource_pk(self) -> str:
        return quote_identifier(self._schema.resource_pk_column)

    def _version_resource_fk(self) -> str:
        return quote_identifier(self._schema.version_resource_fk_column)

    def _resource_type(self) -> str:
        return quote_identifier(self._schema.resource_type_column)

    def _fhir_id(self) -> str:
        return quote_identifier(self._schema.fhir_id_column)

    def _current_version(self) -> str:
        return quote_identifier(self._schema.current_version_column)

    def _version_number(self) -> str:
        return quote_identifier(self._schema.version_number_column)

    def _updated_at(self) -> str:
        return quote_identifier(self._schema.updated_at_column)

    def _deleted_at(self) -> str:
        return quote_identifier(self._schema.deleted_at_column)

    def _encoding(self) -> str:
        return quote_identifier(self._schema.encoding_column)

    def _text_vc(self) -> str:
        return quote_identifier(self._schema.text_vc_column)
