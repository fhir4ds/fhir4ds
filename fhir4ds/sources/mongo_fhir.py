"""
fhir4ds.sources.mongo_fhir
==========================
SourceAdapter for Mongo-backed FHIR servers.

The adapter reads current FHIR resources in place through DuckDB's community
``mongo`` extension and projects them to the standard FHIR4DS ``resources``
view. Runtime analytics stay read-only and use ``mongo_scan`` rather than a
Python MongoDB client.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fhir4ds.sources.base import (
    SchemaValidationError,
    quote_identifier,
    quote_sql_literal,
    validate_schema,
)

MongoCollectionStrategy = Literal["per_resource", "explicit", "shared"]

_MONGO_ATTACHMENT_NAME = "fhir4ds_mongo"
_DEFAULT_BASE_VERSION = "4_0_0"
_DEFAULT_HIDDEN_TAG_SYSTEM = (
    "https://fhir.icanbwell.com/4_0_0/CodeSystem/server-behavior"
)
_DEFAULT_HIDDEN_TAG_CODE = "hidden"
_DEFAULT_PATIENT_REFERENCE_PATHS = (
    "$.subject.reference",
    "$.patient.reference",
    "$.beneficiary.reference",
)
_DEFAULT_SCRUB_PRIVATE_FIELDS = (
    "_id",
    "_uuid",
    "_sourceId",
    "_sourceAssigningAuthority",
)
_MONGO_STRATEGIES = {"per_resource", "explicit", "shared"}
_SENSITIVE_QUERY_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "credential",
    "authmechanismproperties",
    "tlscertificatekeyfilepassword",
    "aws_session_token",
)


def _require_non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    if not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_json_path(value: Any, name: str) -> str:
    path = _require_non_empty_string(value, name)
    if path != "$" and not path.startswith("$."):
        raise ValueError(f"{name} must be '$' or start with '$.', got {path!r}")
    if ".." in path:
        raise ValueError(f"{name} must not contain empty JSON path segments")
    return path


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping, got {type(value).__name__}")
    return value


def _json_path_to_mongo_key(path: str) -> str:
    """Convert a simple JSONPath-like string to a Mongo dotted field path."""
    path = _require_json_path(path, "json path")
    if path == "$":
        return ""
    parts = path[2:].split(".")
    if any(not part for part in parts):
        raise ValueError(f"Unsupported empty JSON path segment in {path!r}")
    return ".".join(parts)


def _join_mongo_path(base_path: str, relative_path: str) -> str:
    base_key = _json_path_to_mongo_key(base_path)
    relative_key = _json_path_to_mongo_key(relative_path)
    if not base_key:
        return relative_key
    if not relative_key:
        return base_key
    return f"{base_key}.{relative_key}"


def _redact_mongo_uri(uri: str) -> str:
    """
    Redact credentials from a Mongo URI for user-facing error messages.

    The helper is intentionally conservative: any parse failure returns a
    generic redacted marker instead of risking credential disclosure.
    """
    try:
        parsed = urlsplit(uri)
        if parsed.scheme not in {"mongodb", "mongodb+srv"}:
            return "<redacted-mongo-uri>"

        netloc = parsed.netloc
        if "@" in netloc:
            _, host_part = netloc.rsplit("@", 1)
            netloc = f"***:***@{host_part}"

        query_parts = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            key_lower = key.lower()
            if any(part in key_lower for part in _SENSITIVE_QUERY_KEY_PARTS):
                query_parts.append((key, "***"))
            else:
                query_parts.append((key, value))
        query = urlencode(query_parts, doseq=True, quote_via=quote)
        return urlunsplit(
            (parsed.scheme, netloc, parsed.path, query, parsed.fragment)
        )
    except Exception:
        return "<redacted-mongo-uri>"


def _copy_filter(value: Mapping[str, Any] | None, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    mapping = _require_mapping(value, name)
    return dict(mapping)


def _normalize_patient_scope(patient_ids: Sequence[str] | None) -> tuple[str, ...] | None:
    if patient_ids is None:
        return None
    if isinstance(patient_ids, str):
        raise TypeError("patient_ids must be a sequence of strings, not a string")
    normalized = []
    for index, patient_id in enumerate(patient_ids):
        if not isinstance(patient_id, str):
            raise TypeError(
                f"patient_ids[{index}] must be a string, got {type(patient_id).__name__}"
            )
        if patient_id:
            normalized.append(patient_id)
    return tuple(sorted(set(normalized)))


@dataclass(frozen=True)
class MongoResourceCollection:
    """
    Mapping from one FHIR resource type to one Mongo collection.

    ``resource_path``, ``id_path``, and ``resource_type_path`` are JSON paths
    into the row materialized by DuckDB's ``mongo_scan``. This supports both
    layouts where the FHIR resource is the root document and layouts where it is
    wrapped under a field such as ``resource`` or ``payload``.
    """

    resource_type: str
    collection_name: str
    resource_path: str = "$"
    id_path: str = "$.id"
    resource_type_path: str = "$.resourceType"
    current_filter: Mapping[str, Any] | None = None
    deleted_filter: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_type",
            _require_non_empty_string(self.resource_type, "resource_type"),
        )
        object.__setattr__(
            self,
            "collection_name",
            _require_non_empty_string(self.collection_name, "collection_name"),
        )
        object.__setattr__(
            self, "resource_path", _require_json_path(self.resource_path, "resource_path")
        )
        object.__setattr__(
            self, "id_path", _require_json_path(self.id_path, "id_path")
        )
        object.__setattr__(
            self,
            "resource_type_path",
            _require_json_path(self.resource_type_path, "resource_type_path"),
        )
        object.__setattr__(
            self,
            "current_filter",
            _copy_filter(self.current_filter, "current_filter"),
        )
        object.__setattr__(
            self,
            "deleted_filter",
            _copy_filter(self.deleted_filter, "deleted_filter"),
        )


@dataclass(frozen=True)
class MongoFhirServerSchema:
    """
    Configurable Mongo FHIR server schema mapping.

    The default configuration matches the Helix / ``icanbwell/fhir-server``
    convention where current resources live in per-resource collections such as
    ``Patient_4_0_0``. Use ``collections`` for fully custom layouts.
    """

    database_name: str = "fhir"
    base_version: str = _DEFAULT_BASE_VERSION
    collection_strategy: MongoCollectionStrategy = "per_resource"
    resource_types: tuple[str, ...] | list[str] | None = None
    collections: tuple[MongoResourceCollection, ...] | list[MongoResourceCollection] | None = None
    collection_mappings: Mapping[str, str] | None = None
    shared_collection: str | None = None
    shared_resource_path: str = "$"
    shared_id_path: str = "$.id"
    shared_resource_type_path: str = "$.resourceType"
    shared_current_filter: Mapping[str, Any] | None = None
    shared_deleted_filter: Mapping[str, Any] | None = None
    sample_size: int | None = -1
    include_hidden: bool = False
    hidden_tag_system: str = _DEFAULT_HIDDEN_TAG_SYSTEM
    hidden_tag_code: str = _DEFAULT_HIDDEN_TAG_CODE
    patient_reference_paths: tuple[str, ...] | list[str] = _DEFAULT_PATIENT_REFERENCE_PATHS
    scrub_private_fields: tuple[str, ...] | list[str] = _DEFAULT_SCRUB_PRIVATE_FIELDS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "database_name",
            _require_non_empty_string(self.database_name, "database_name"),
        )
        object.__setattr__(
            self,
            "base_version",
            _require_non_empty_string(self.base_version, "base_version"),
        )
        if not isinstance(self.collection_strategy, str):
            raise TypeError(
                "collection_strategy must be a string, got "
                f"{type(self.collection_strategy).__name__}"
            )
        if self.collection_strategy not in _MONGO_STRATEGIES:
            raise ValueError(
                "collection_strategy must be one of "
                f"{tuple(sorted(_MONGO_STRATEGIES))}, got {self.collection_strategy!r}"
            )
        if self.resource_types is not None:
            resource_types = tuple(
                _require_non_empty_string(rt, "resource_type")
                for rt in self.resource_types
            )
            if not resource_types:
                raise ValueError("resource_types must not be empty when provided")
            object.__setattr__(self, "resource_types", resource_types)
        if self.collections is not None:
            collections = tuple(self.collections)
            if not collections:
                raise ValueError("collections must not be empty when provided")
            for collection in collections:
                if not isinstance(collection, MongoResourceCollection):
                    raise TypeError(
                        "collections must contain MongoResourceCollection instances"
                    )
            object.__setattr__(self, "collections", collections)
        if self.collection_mappings is not None:
            mappings = _require_mapping(self.collection_mappings, "collection_mappings")
            if not mappings:
                raise ValueError("collection_mappings must not be empty when provided")
            normalized = {
                _require_non_empty_string(resource_type, "resource_type"):
                _require_non_empty_string(collection_name, "collection_name")
                for resource_type, collection_name in mappings.items()
            }
            object.__setattr__(self, "collection_mappings", normalized)
        if self.collections is not None and self.collection_mappings is not None:
            raise ValueError("collections and collection_mappings are mutually exclusive")
        if self.shared_collection is not None:
            object.__setattr__(
                self,
                "shared_collection",
                _require_non_empty_string(self.shared_collection, "shared_collection"),
            )
        object.__setattr__(
            self,
            "shared_resource_path",
            _require_json_path(self.shared_resource_path, "shared_resource_path"),
        )
        object.__setattr__(
            self,
            "shared_id_path",
            _require_json_path(self.shared_id_path, "shared_id_path"),
        )
        object.__setattr__(
            self,
            "shared_resource_type_path",
            _require_json_path(
                self.shared_resource_type_path,
                "shared_resource_type_path",
            ),
        )
        object.__setattr__(
            self,
            "shared_current_filter",
            _copy_filter(self.shared_current_filter, "shared_current_filter"),
        )
        object.__setattr__(
            self,
            "shared_deleted_filter",
            _copy_filter(self.shared_deleted_filter, "shared_deleted_filter"),
        )
        if self.sample_size is not None:
            if not isinstance(self.sample_size, int):
                raise TypeError(
                    f"sample_size must be an integer or None, got {type(self.sample_size).__name__}"
                )
            if self.sample_size == 0 or self.sample_size < -1:
                raise ValueError("sample_size must be -1, a positive integer, or None")
        if not isinstance(self.include_hidden, bool):
            raise TypeError(
                f"include_hidden must be a bool, got {type(self.include_hidden).__name__}"
            )
        object.__setattr__(
            self,
            "hidden_tag_system",
            _require_non_empty_string(self.hidden_tag_system, "hidden_tag_system"),
        )
        object.__setattr__(
            self,
            "hidden_tag_code",
            _require_non_empty_string(self.hidden_tag_code, "hidden_tag_code"),
        )
        patient_paths = tuple(
            _require_json_path(path, "patient_reference_paths item")
            for path in self.patient_reference_paths
        )
        if not patient_paths:
            raise ValueError("patient_reference_paths must not be empty")
        object.__setattr__(self, "patient_reference_paths", patient_paths)
        scrub_fields = tuple(
            _require_non_empty_string(field, "scrub_private_fields item")
            for field in self.scrub_private_fields
        )
        object.__setattr__(self, "scrub_private_fields", scrub_fields)
        self._validate_strategy_options()

    def _validate_strategy_options(self) -> None:
        if self.collection_strategy == "per_resource":
            if self.collections is not None or self.collection_mappings is not None:
                raise ValueError(
                    "collection_strategy='per_resource' cannot be combined with "
                    "collections or collection_mappings"
                )
            if self.shared_collection is not None:
                raise ValueError(
                    "collection_strategy='per_resource' cannot be combined with "
                    "shared_collection"
                )
        elif self.collection_strategy == "explicit":
            if self.shared_collection is not None:
                raise ValueError(
                    "collection_strategy='explicit' cannot be combined with "
                    "shared_collection"
                )
        elif self.collection_strategy == "shared":
            if self.collections is not None or self.collection_mappings is not None:
                raise ValueError(
                    "collection_strategy='shared' cannot be combined with "
                    "collections or collection_mappings"
                )


class MongoFhirServerSource:
    """
    SourceAdapter for Mongo-backed FHIR servers.

    The adapter creates the standard FHIR4DS ``resources`` view from one or
    more Mongo collections using DuckDB's community ``mongo`` extension.
    """

    def __init__(
        self,
        connection_string: str,
        *,
        schema: MongoFhirServerSchema | None = None,
        attachment_name: str = _MONGO_ATTACHMENT_NAME,
        install_extension: bool = True,
    ) -> None:
        self._connection_string = _require_non_empty_string(
            connection_string, "connection_string"
        )
        self._schema = schema or MongoFhirServerSchema()
        if not isinstance(self._schema, MongoFhirServerSchema):
            raise TypeError(
                f"schema must be a MongoFhirServerSchema, got {type(self._schema).__name__}"
            )
        self._attachment_name = _require_non_empty_string(
            attachment_name, "attachment_name"
        )
        if not isinstance(install_extension, bool):
            raise TypeError(
                f"install_extension must be a bool, got {type(install_extension).__name__}"
            )
        self._install_extension = install_extension
        self._patient_scope: tuple[str, ...] | None = None
        self._attached = False
        self._con: Any | None = None

    def register(self, con: Any) -> None:
        """
        Load DuckDB's Mongo extension and create the ``resources`` view.
        """
        self._load_mongo_extension(con)
        try:
            self._create_resources_view(con)
        except SchemaValidationError:
            raise
        except Exception as exc:
            raise SchemaValidationError(
                f"{self.__class__.__name__} failed to create the 'resources' view "
                f"from Mongo source {_redact_mongo_uri(self._connection_string)}: {exc}"
            ) from exc
        self._con = con
        validate_schema(con, self.__class__.__name__)

    def unregister(self, con: Any) -> None:
        """Drop the ``resources`` view and detach any discovery attachment."""
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
        """MongoFhirServerSource v1 is read-only and does not expose deltas."""
        return False

    def set_patient_scope(self, patient_ids: Sequence[str] | None) -> None:
        """
        Restrict the mounted ``resources`` view to a batch of patient IDs.

        ``None`` clears the source-level scope. This method is intended for DQM
        materialization workers that already know which patients changed.
        """
        self._patient_scope = _normalize_patient_scope(patient_ids)
        if self._con is not None:
            self._create_resources_view(self._con)

    def clear_patient_scope(self) -> None:
        """Clear any materialization-time patient scope."""
        self.set_patient_scope(None)

    def _create_resources_view(self, con: Any) -> None:
        con.execute(
            f"CREATE OR REPLACE VIEW resources AS {self._current_resources_select(con)}"
        )

    def _load_mongo_extension(self, con: Any) -> None:
        try:
            if self._install_extension:
                con.execute("INSTALL mongo FROM community")
            con.execute("LOAD mongo")
        except Exception as exc:
            raise SchemaValidationError(
                "DuckDB community extension 'mongo' could not be installed or "
                f"loaded for Mongo source {_redact_mongo_uri(self._connection_string)}. "
                "Install/load the extension manually or check network access to "
                "DuckDB community extensions."
            ) from exc

    def _current_resources_select(self, con: Any | None = None) -> str:
        collection_specs = self._collection_specs()
        if collection_specs is None:
            if con is None:
                raise SchemaValidationError(
                    "MongoFhirServerSource requires resource_types, collections, "
                    "or collection_mappings when no DuckDB connection is available "
                    "for catalog discovery."
                )
            collection_specs = self._discover_collection_specs(con)

        selects = [self._collection_select(spec) for spec in collection_specs]
        if not selects:
            raise SchemaValidationError(
                "MongoFhirServerSource resolved zero Mongo collections. Provide "
                "resource_types, collections, or collection_mappings."
            )
        return "\nUNION ALL\n".join(selects)

    def _collection_specs(self) -> tuple[MongoResourceCollection, ...] | None:
        schema = self._schema
        if schema.collection_strategy == "per_resource":
            if schema.resource_types is None:
                return None
            return tuple(
                MongoResourceCollection(
                    resource_type=resource_type,
                    collection_name=f"{resource_type}_{schema.base_version}",
                )
                for resource_type in schema.resource_types
            )

        if schema.collection_strategy == "explicit":
            if schema.collections is not None:
                return schema.collections
            if schema.collection_mappings is None:
                raise ValueError(
                    "collection_strategy='explicit' requires collections or "
                    "collection_mappings"
                )
            resource_types = schema.resource_types or tuple(schema.collection_mappings)
            missing = sorted(set(resource_types) - set(schema.collection_mappings))
            if missing:
                raise ValueError(
                    "collection_mappings is missing collection names for resource "
                    f"type(s): {missing}"
                )
            return tuple(
                MongoResourceCollection(
                    resource_type=resource_type,
                    collection_name=schema.collection_mappings[resource_type],
                )
                for resource_type in resource_types
            )

        if schema.collection_strategy == "shared":
            if schema.shared_collection is None or schema.resource_types is None:
                raise ValueError(
                    "collection_strategy='shared' requires shared_collection and "
                    "resource_types"
                )
            return tuple(
                MongoResourceCollection(
                    resource_type=resource_type,
                    collection_name=schema.shared_collection,
                    resource_path=schema.shared_resource_path,
                    id_path=schema.shared_id_path,
                    resource_type_path=schema.shared_resource_type_path,
                    current_filter=schema.shared_current_filter,
                    deleted_filter=schema.shared_deleted_filter,
                )
                for resource_type in schema.resource_types
            )

        raise ValueError(f"Unsupported collection_strategy: {schema.collection_strategy}")

    def _discover_collection_specs(self, con: Any) -> tuple[MongoResourceCollection, ...]:
        att = quote_identifier(self._attachment_name)
        try:
            con.execute(
                f"ATTACH IF NOT EXISTS {quote_sql_literal(self._connection_string)} "
                f"AS {att} (TYPE MONGO)"
            )
            self._attached = True
            rows = con.execute("SHOW TABLES").fetchall()
        except Exception as exc:
            raise SchemaValidationError(
                "Mongo collection discovery is unavailable for "
                f"{_redact_mongo_uri(self._connection_string)}. Provide "
                "resource_types, collections, or collection_mappings explicitly."
            ) from exc

        pattern = re.compile(rf"^([A-Z][A-Za-z0-9]*)_{re.escape(self._schema.base_version)}$")
        specs: list[MongoResourceCollection] = []
        for row in rows:
            collection_name = str(row[0])
            match = pattern.match(collection_name)
            if match and not collection_name.endswith("_History"):
                specs.append(
                    MongoResourceCollection(
                        resource_type=match.group(1),
                        collection_name=collection_name,
                    )
                )
        if not specs:
            raise SchemaValidationError(
                "Mongo collection discovery did not find current-resource "
                f"collections matching '*_{self._schema.base_version}'. Provide "
                "resource_types, collections, or collection_mappings explicitly."
            )
        return tuple(specs)

    def _collection_select(self, spec: MongoResourceCollection) -> str:
        row_json = "row_json"
        resource_json = "resource_json"
        scrubbed_resource = self._scrubbed_resource_expression(resource_json)
        id_expr = f"json_extract_string({row_json}, {quote_sql_literal(spec.id_path)})"
        resource_type_expr = (
            f"json_extract_string({row_json}, {quote_sql_literal(spec.resource_type_path)})"
        )
        patient_ref_expr = self._patient_ref_expression(
            resource_type_expr=resource_type_expr,
            id_expr=id_expr,
            resource_expr=resource_json,
        )
        scan_expr = self._mongo_scan_expression(spec)
        return f"""
            SELECT
                {id_expr}::VARCHAR AS id,
                {resource_type_expr}::VARCHAR AS resourceType,
                {scrubbed_resource}::JSON AS resource,
                {patient_ref_expr}::VARCHAR AS patient_ref
            FROM (
                SELECT
                    to_json(src)::JSON AS row_json,
                    json_extract(to_json(src)::JSON, {quote_sql_literal(spec.resource_path)})::JSON
                        AS resource_json
                FROM {scan_expr} AS src
            ) mounted
        """

    def _mongo_scan_expression(self, spec: MongoResourceCollection) -> str:
        filter_json = self._filter_json(spec)
        args = [
            quote_sql_literal(self._connection_string),
            quote_sql_literal(self._schema.database_name),
            quote_sql_literal(spec.collection_name),
            f"filter := {quote_sql_literal(filter_json)}",
        ]
        if self._schema.sample_size is not None:
            args.append(f"sample_size := {self._schema.sample_size}")
        return f"mongo_scan({', '.join(args)})"

    def _filter_json(self, spec: MongoResourceCollection) -> str:
        filters: list[dict[str, Any]] = []
        resource_type_key = _json_path_to_mongo_key(spec.resource_type_path)
        if resource_type_key:
            filters.append({resource_type_key: spec.resource_type})
        if spec.current_filter:
            filters.append(dict(spec.current_filter))
        if spec.deleted_filter:
            filters.append({"$nor": [dict(spec.deleted_filter)]})
        patient_filter = self._patient_scope_filter(spec)
        if patient_filter:
            filters.append(patient_filter)
        if not self._schema.include_hidden:
            hidden_key = _join_mongo_path(spec.resource_path, "$.meta.tag")
            if hidden_key:
                filters.append(
                    {
                        hidden_key: {
                            "$not": {
                                "$elemMatch": {
                                    "system": self._schema.hidden_tag_system,
                                    "code": self._schema.hidden_tag_code,
                                }
                            }
                        }
                    }
                )

        if not filters:
            filter_obj: dict[str, Any] = {}
        elif len(filters) == 1:
            filter_obj = filters[0]
        else:
            filter_obj = {"$and": filters}
        return json.dumps(filter_obj, separators=(",", ":"), sort_keys=True)

    def _patient_scope_filter(self, spec: MongoResourceCollection) -> dict[str, Any] | None:
        patient_ids = self._patient_scope
        if patient_ids is None:
            return None
        if not patient_ids:
            return {"_id": {"$in": []}}
        if spec.resource_type == "Patient":
            id_key = _json_path_to_mongo_key(spec.id_path)
            return {(id_key or "_id"): {"$in": list(patient_ids)}}

        local_refs = [f"Patient/{patient_id}" for patient_id in patient_ids]
        escaped = "|".join(re.escape(patient_id) for patient_id in patient_ids)
        absolute_ref_regex = rf"^https?://.*/Patient/(?:{escaped})$"
        clauses: list[dict[str, Any]] = []
        for path in self._schema.patient_reference_paths:
            key = _join_mongo_path(spec.resource_path, path)
            if not key:
                continue
            clauses.append({key: {"$in": local_refs}})
            clauses.append({key: {"$regex": absolute_ref_regex}})
        if not clauses:
            return {"_id": {"$in": []}}
        return {"$or": clauses}

    def _scrubbed_resource_expression(self, resource_expr: str) -> str:
        if not self._schema.scrub_private_fields:
            return resource_expr
        patch = dict.fromkeys(self._schema.scrub_private_fields)
        patch_json = json.dumps(patch, separators=(",", ":"), sort_keys=True)
        return f"json_merge_patch({resource_expr}, {quote_sql_literal(patch_json)}::JSON)"

    def _patient_ref_expression(
        self,
        *,
        resource_type_expr: str,
        id_expr: str,
        resource_expr: str,
    ) -> str:
        candidates = [f"CASE WHEN {resource_type_expr} = 'Patient' THEN {id_expr} END"]
        local_pattern = quote_sql_literal(r"^Patient/([^/?#]+)$")
        absolute_pattern = quote_sql_literal(r"^https?://.*/Patient/([^/?#]+)$")
        for path in self._schema.patient_reference_paths:
            path_literal = quote_sql_literal(path)
            ref_expr = f"json_extract_string({resource_expr}, {path_literal})"
            candidates.append(
                f"NULLIF(regexp_extract({ref_expr}, {local_pattern}, 1), '')"
            )
            candidates.append(
                f"NULLIF(regexp_extract({ref_expr}, {absolute_pattern}, 1), '')"
            )
        return f"COALESCE({', '.join(candidates)})"


__all__ = [
    "MongoCollectionStrategy",
    "MongoResourceCollection",
    "MongoFhirServerSchema",
    "MongoFhirServerSource",
]
