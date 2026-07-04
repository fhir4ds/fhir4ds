# src/cql_py/loader/fhir_loader.py
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Union, List, Optional, Any, TYPE_CHECKING
from urllib.parse import urlparse
from weakref import WeakKeyDictionary, WeakSet
try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

from fhir4ds.sources.base import quote_identifier

if TYPE_CHECKING:  # pragma: no cover - import-time only
    # Forward-import AutoCoder and NotesPipeline only for type checkers —
    # never imported at runtime to preserve the loader's zero-dep default.
    # Both are passed in by callers; we never construct one inside the
    # loader.
    from .auto_coder import AutoCoder
    from .notes_pipeline import NotesPipeline

_logger = logging.getLogger(__name__)

# Per-connection caches. WeakKeyDictionary ensures entries are cleaned up
# when DuckDB connections are garbage-collected.  Protected by a lock for
# thread safety when multiple threads register UDFs on different connections.
_CACHE_LOCK = threading.Lock()
_VALUESET_UDF_CACHE_BY_CONNECTION = WeakKeyDictionary()
_VALUESET_UDF_REGISTERED_CONNECTIONS = WeakSet()
_FHIR_RESOURCE_TYPE_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_FHIR_ID_RE = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")


def _validate_resource_identity(resource: dict) -> tuple[str, str | None]:
    resource_type = resource.get("resourceType")
    if not resource_type:
        raise ValueError(
            "Resource must have a 'resourceType' field. "
            f"Got keys: {sorted(resource.keys())}"
        )
    if not isinstance(resource_type, str):
        raise ValueError(
            f"'resourceType' must be a string, got {type(resource_type).__name__}: "
            f"{resource_type!r}"
        )
    if not _FHIR_RESOURCE_TYPE_RE.match(resource_type):
        raise ValueError(
            f"'resourceType' must be an ASCII FHIR resource type name, got {resource_type!r}"
        )

    resource_id = resource.get("id")
    if resource_id is not None:
        if not isinstance(resource_id, str):
            raise ValueError(
                f"Resource 'id' must be a string per FHIR R4 spec, "
                f"got {type(resource_id).__name__}: {resource_id!r}"
            )
        if not _FHIR_ID_RE.match(resource_id):
            raise ValueError(
                f"Resource 'id' must match the FHIR id pattern [A-Za-z0-9-.]{{1,64}}, "
                f"got {resource_id!r}"
            )
    return resource_type, resource_id


def _serialize_resource(resource: dict) -> str:
    try:
        return json.dumps(resource, allow_nan=False)
    except ValueError as exc:
        raise ValueError(
            "Resource contains values that cannot be represented as standard JSON "
            "(for example NaN or Infinity)."
        ) from exc


def _extract_codes_from_valueset_resource(valueset: dict) -> list[dict[str, str | None]]:
    """Extract codes from a raw FHIR ValueSet compose/expansion resource."""
    codes: list[dict[str, str | None]] = []

    expansion_contains = valueset.get("expansion", {}).get("contains", [])
    if isinstance(expansion_contains, list):
        for item in expansion_contains:
            if not isinstance(item, dict):
                raise TypeError("ValueSet.expansion.contains entries must be objects")
            system = item.get("system")
            code = item.get("code")
            if system is not None or code is not None:
                codes.append({
                    "system": system,
                    "code": code,
                    "display": item.get("display"),
                })

    compose_includes = valueset.get("compose", {}).get("include", [])
    if isinstance(compose_includes, list):
        for include in compose_includes:
            if not isinstance(include, dict):
                raise TypeError("ValueSet.compose.include entries must be objects")
            system = include.get("system")
            concepts = include.get("concept", [])
            if concepts is None:
                concepts = []
            if not isinstance(concepts, list):
                raise TypeError("ValueSet.compose.include.concept must be a list")
            for concept in concepts:
                if not isinstance(concept, dict):
                    raise TypeError("ValueSet.compose.include.concept entries must be objects")
                codes.append({
                    "system": system,
                    "code": concept.get("code"),
                    "display": concept.get("display"),
                })

    return codes


class FHIRDataLoader:
    """
    Load FHIR resources into DuckDB for CQL evaluation.

    Creates a single `resources` table with columns:
    - id VARCHAR
    - resourceType VARCHAR
    - resource JSON
    - patient_ref VARCHAR

    Example:
        loader = FHIRDataLoader(con)
        loader.load_directory(Path("./fhir-data"))
        loader.load_file(Path("./bundle.json"))
        loader.load_ndjson(Path("./patients.ndjson"))
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        table_name: str = "resources",
        create_table: bool = True,
        auto_coder: "Optional[AutoCoder]" = None,
        notes_pipeline: "Optional[NotesPipeline]" = None,
    ):
        if con is None:
            raise TypeError("Expected a DuckDB connection for 'con', got None")
        if not isinstance(con, duckdb.DuckDBPyConnection):
            raise TypeError(
                f"Expected a DuckDB connection for 'con', got {type(con).__name__}"
            )
        self.con = con
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(
                f"table_name must be a valid SQL identifier, got {table_name!r}"
            )
        self.table_name = table_name
        self._quoted_table_name = quote_identifier(table_name)
        # Optional Phase 2 auto-coder. With ``auto_coder=None`` (default),
        # loader behavior is byte-identical to pre-Phase-2 (INV-1).
        # Stored on the instance so all entry points (load_resource,
        # load_resources, load_bundle/load_file/load_ndjson/load_directory/
        # load_from_url which delegate) get the augmentation hook for free.
        self._auto_coder = auto_coder
        # Optional Phase 4 notes pipeline. With ``notes_pipeline=None``
        # (default), loader behavior is byte-identical to pre-Phase-4
        # (INV-1 / Phase 4 SCOPE REDUCTION invariant). When set, the
        # loader appends derived Conditions alongside each source
        # resource via ``notes_pipeline.extract_conditions(resource)``.
        self._notes_pipeline = notes_pipeline
        # Share one mutable cache per DuckDB connection so repeated FHIRDataLoader
        # instances update the same _in_valueset_python closure in-place.
        with _CACHE_LOCK:
            shared_cache = _VALUESET_UDF_CACHE_BY_CONNECTION.get(con)
            if shared_cache is None:
                shared_cache = {}
                _VALUESET_UDF_CACHE_BY_CONNECTION[con] = shared_cache
        self._valueset_udf_cache: dict = shared_cache
        if create_table:
            self._create_table()

    def _create_table(self) -> None:
        """Create the resources table if it doesn't exist.

        Deduplication is handled at the application level by
        ``load_resource()``, which performs delete-before-insert for
        resources with matching (id, resourceType).  No UNIQUE index
        is added because external callers (e.g., the benchmark runner)
        may legitimately insert rows with the same (id, resourceType)
        but different context (e.g., source_measure scoping).
        """
        tbl = self._quoted_table_name
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS {tbl} (
                id VARCHAR,
                resourceType VARCHAR,
                resource JSON,
                patient_ref VARCHAR
            )
        """)
        self._register_resolve_macro()

    def _register_resolve_macro(self) -> None:
        """Register the CQL resolve() macro that follows FHIR references.

        The macro performs a correlated subquery against the resources table
        to look up the referenced resource by ``ResourceType/id``, a full URL
        ending in ``ResourceType/id``, a bare resource id, or a JSON Reference
        object containing any of those reference forms.
        """
        tbl = self._quoted_table_name
        try:
            self.con.execute(f"""
                CREATE OR REPLACE MACRO resolve(ref) AS (
                    WITH _ref AS (
                        SELECT CASE
                            WHEN ref IS NULL THEN NULL
                            WHEN LTRIM(ref::VARCHAR) LIKE '{{%'
                                THEN json_extract_string(ref::VARCHAR, '$.reference')
                            ELSE TRIM(BOTH '"' FROM ref::VARCHAR)
                        END AS raw_ref
                    )
                    SELECT r.resource FROM {tbl} r
                    CROSS JOIN _ref
                    WHERE ref IS NOT NULL
                    AND raw_ref IS NOT NULL
                    AND r.id = regexp_replace(split_part(raw_ref, '/', -1), '^urn:uuid:', '')
                    AND (
                        split_part(raw_ref, '/', -2) = ''
                        OR r.resourceType = split_part(raw_ref, '/', -2)
                    )
                    LIMIT 1
                )
            """)
        except Exception:
            _logger.debug("resolve() macro registration skipped (table may not exist)")

    def _extract_patient_ref(self, resource: dict) -> Optional[str]:
        """
        Extract patient reference from a FHIR resource.

        - For Patient resources: returns the resource id
        - For other resources: extracts from subject.reference or patient.reference
        - Returns None if no patient link found
        """
        resource_type = resource.get("resourceType")

        if resource_type == "Patient":
            return resource.get("id")

        for path in ("subject", "patient", "beneficiary"):
            ref_obj = resource.get(path)
            if ref_obj and isinstance(ref_obj, dict):
                reference = ref_obj.get("reference", "")
                if reference:
                    # Strip urn:uuid: prefix for bundle-local references
                    if reference.startswith("urn:uuid:"):
                        return reference[9:]  # len("urn:uuid:") == 9
                    if "/" in reference:
                        return reference.split("/")[-1]
                    return reference

        return None

    def load_resource(self, resource: dict) -> None:
        """Load a single FHIR resource.

        If a resource with the same (id, resourceType) already exists,
        it is replaced with the new version.  Resources without an id
        are inserted without deduplication.

        Raises:
            TypeError: If resource is not a dict.
            ValueError: If resource lacks a valid 'resourceType' field.
        """
        if not isinstance(resource, dict):
            raise TypeError(
                f"Expected dict, got {type(resource).__name__}"
            )
        # Phase 2 augmentation hook — runs BEFORE validate/serialize so the
        # auto-coder can append Codings to text-only CodeableConcepts. With
        # ``self._auto_coder is None`` (the default) this branch is skipped
        # entirely and behavior is byte-identical to pre-Phase-2 (INV-1).
        if self._auto_coder is not None:
            self._auto_coder.augment_resource(resource)
        resource_type, resource_id = _validate_resource_identity(resource)
        patient_ref = self._extract_patient_ref(resource)
        resource_json = _serialize_resource(resource)

        if resource_id is not None and resource_type is not None:
            # Delete existing resource with same identity, then insert
            self.con.execute(
                f"DELETE FROM {self._quoted_table_name} WHERE id = ? AND resourceType = ?",
                [resource_id, resource_type],
            )
        self.con.execute(
            f"INSERT INTO {self._quoted_table_name} VALUES (?, ?, ?, ?)",
            [resource_id, resource_type, resource_json, patient_ref],
        )

        # Phase 4 notes-pipeline hook — runs AFTER the source resource is
        # loaded so derived Conditions join the same batch. With
        # ``self._notes_pipeline is None`` (default) this branch is
        # skipped entirely and behavior is byte-identical to pre-Phase-4.
        # ``extract_conditions`` NEVER raises (Phase 4 INV-3) and returns
        # ``[]`` for Condition source resources (Phase 4 INV-4) so batch
        # loads cannot enter an infinite loop.
        if self._notes_pipeline is not None:
            derived = self._notes_pipeline.extract_conditions(resource)
            for derived_resource in derived or []:
                if not isinstance(derived_resource, dict):
                    continue
                try:
                    d_type, d_id = _validate_resource_identity(derived_resource)
                    d_patient_ref = self._extract_patient_ref(derived_resource)
                    d_json = _serialize_resource(derived_resource)
                except (TypeError, ValueError) as exc:
                    _logger.warning(
                        "Skipping invalid derived Condition from %s/%s: %s",
                        resource_type, resource_id, exc,
                    )
                    continue
                if d_id is not None and d_type is not None:
                    self.con.execute(
                        f"DELETE FROM {self._quoted_table_name} WHERE id = ? AND resourceType = ?",
                        [d_id, d_type],
                    )
                self.con.execute(
                    f"INSERT INTO {self._quoted_table_name} VALUES (?, ?, ?, ?)",
                    [d_id, d_type, d_json, d_patient_ref],
                )

    def load_resources(self, resources: list[dict]) -> int:
        """Load multiple FHIR resources in a single batch.

        Uses executemany for better performance than individual
        load_resource() calls. Deduplicates by (id, resourceType) — when
        the same identity appears multiple times, only the last entry is kept.

        Args:
            resources: List of FHIR resource dicts.

        Returns:
            Number of unique resources loaded.

        Raises:
            TypeError: If any resource is not a dict.
            ValueError: If any resource lacks a valid 'resourceType' field.
        """
        if resources is None:
            raise TypeError("Expected list of FHIR resource dicts, got None")
        if not isinstance(resources, list):
            raise TypeError(
                f"Expected list of FHIR resource dicts, got {type(resources).__name__}"
            )
        if not resources:
            return 0

        # Build rows and deduplicate: last-write-wins for same (id, resourceType)
        seen: dict[tuple[str, str], int] = {}
        rows: list[tuple] = []
        dedup_count = 0
        for resource in resources:
            if not isinstance(resource, dict):
                raise TypeError(f"Expected dict, got {type(resource).__name__}")
            # Phase 2 augmentation hook — runs BEFORE validate/serialize so
            # the auto-coder can append Codings. With ``self._auto_coder
            # is None`` (the default) this branch is skipped entirely and
            # behavior is byte-identical to pre-Phase-2 (INV-1).
            if self._auto_coder is not None:
                self._auto_coder.augment_resource(resource)
            resource_type, resource_id = _validate_resource_identity(resource)
            patient_ref = self._extract_patient_ref(resource)
            resource_json = _serialize_resource(resource)
            row = (resource_id, resource_type, resource_json, patient_ref)
            if resource_id is not None:
                key = (resource_id, resource_type)
                if key in seen:
                    _logger.debug(
                        "Duplicate resource %s/%s — keeping latest",
                        resource_type, resource_id,
                    )
                    rows[seen[key]] = None  # type: ignore[assignment]
                    dedup_count += 1
                seen[key] = len(rows)
            rows.append(row)

            # Phase 4 notes-pipeline hook (batch path). With
            # ``self._notes_pipeline is None`` (default) this branch is
            # skipped entirely and behavior is byte-identical to
            # pre-Phase-4. ``extract_conditions`` NEVER raises (Phase 4
            # INV-3) so a single bad resource cannot poison the batch.
            if self._notes_pipeline is not None:
                derived_list = self._notes_pipeline.extract_conditions(resource)
                for derived_resource in derived_list or []:
                    if not isinstance(derived_resource, dict):
                        continue
                    try:
                        d_type, d_id = _validate_resource_identity(derived_resource)
                        d_patient_ref = self._extract_patient_ref(derived_resource)
                        d_json = _serialize_resource(derived_resource)
                    except (TypeError, ValueError) as exc:
                        _logger.warning(
                            "Skipping invalid derived Condition from %s/%s: %s",
                            resource_type, resource_id, exc,
                        )
                        continue
                    d_row = (d_id, d_type, d_json, d_patient_ref)
                    if d_id is not None:
                        d_key = (d_id, d_type)
                        if d_key in seen:
                            rows[seen[d_key]] = None  # type: ignore[assignment]
                            dedup_count += 1
                        seen[d_key] = len(rows)
                    rows.append(d_row)

        # Filter out replaced duplicates
        final_rows = [r for r in rows if r is not None]
        if dedup_count:
            _logger.info(
                "Loaded %d resources (%d duplicates removed)",
                len(final_rows), dedup_count,
            )

        # Remove existing duplicates in batch
        dedup_keys = [(rid, rtype) for rid, rtype in seen.keys()]
        if dedup_keys:
            self.con.executemany(
                f"DELETE FROM {self._quoted_table_name} WHERE id = ? AND resourceType = ?",
                dedup_keys,
            )

        # Batch insert
        self.con.executemany(
            f"INSERT INTO {self._quoted_table_name} VALUES (?, ?, ?, ?)",
            final_rows,
        )
        return len(final_rows)

    def load_bundle(self, bundle: dict) -> int:
        """
        Load all resources from a FHIR Bundle.

        Returns the number of resources loaded.

        Raises:
            TypeError: If bundle is not a dict.
            ValueError: If bundle is not a FHIR Bundle resource.
        """
        if not isinstance(bundle, dict):
            raise TypeError(
                f"Expected dict for bundle, got {type(bundle).__name__}"
            )
        if bundle.get("resourceType") != "Bundle":
            raise ValueError("Expected a FHIR Bundle resource")

        entries = bundle.get("entry") or []
        if not isinstance(entries, list):
            raise TypeError("Bundle.entry must be a list")

        resources = []
        for index, entry in enumerate(entries):
            if entry is None:
                continue
            if not isinstance(entry, dict):
                raise TypeError(f"Bundle.entry[{index}] must be an object")
            resource = entry.get("resource")
            if resource is None:
                continue
            if not isinstance(resource, dict):
                raise TypeError(f"Bundle.entry[{index}].resource must be an object")
            if resource:
                resources.append(resource)

        if resources:
            return self.load_resources(resources)
        return 0

    def load_file(self, path: Union[str, Path]) -> int:
        """
        Load from a JSON file.

        Automatically detects if it's a Bundle or single resource.
        Returns the number of resources loaded.
        """
        path = Path(path) if not isinstance(path, Path) else path
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise TypeError(
                f"FHIR JSON file {path} must contain an object resource or Bundle, "
                f"got {type(data).__name__}"
            )
        resource_type = data.get("resourceType")

        if resource_type == "Bundle":
            return self.load_bundle(data)
        else:
            self.load_resource(data)
            return 1

    def load_ndjson(self, path: Union[str, Path], *, strict: bool = True) -> int:
        """
        Load from an NDJSON file (one resource per line).

        Returns the number of resources loaded.

        Args:
            path: Path to the NDJSON file.
            strict: If True (default), raise on malformed JSON to prevent
                partial loads. If False, skip bad lines with a warning and
                continue loading valid resources.

        Raises:
            ValueError: If strict=True and any line contains malformed JSON.
        """
        import logging
        _logger = logging.getLogger("fhir4ds.loader")
        path = Path(path) if not isinstance(path, Path) else path
        resources = []
        with open(path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        resource = json.loads(line)
                    except json.JSONDecodeError as e:
                        if strict:
                            raise ValueError(
                                f"Malformed JSON at line {line_num} in {path}: {e}"
                            ) from e
                        _logger.warning(
                            "Skipping malformed JSON at line %d in %s: %s",
                            line_num, path, e,
                        )
                        continue
                    if not strict:
                        try:
                            if not isinstance(resource, dict):
                                raise TypeError(
                                    f"Expected dict, got {type(resource).__name__}"
                                )
                            _validate_resource_identity(resource)
                            _serialize_resource(resource)
                        except (TypeError, ValueError) as e:
                            _logger.warning(
                                "Skipping invalid FHIR resource at line %d in %s: %s",
                                line_num, path, e,
                            )
                            continue
                    resources.append(resource)

        return self.load_resources(resources)

    def load_directory(
        self,
        path: Union[str, Path],
        recursive: bool = True,
        extensions: List[str] = None
    ) -> int:
        """
        Load all supported files from a directory.

        Non-FHIR files (missing resourceType, malformed JSON) are skipped
        with a warning logged. Returns the total number of resources loaded.

        Raises:
            FileNotFoundError: If the directory does not exist.
            NotADirectoryError: If the path exists but is not a directory.
        """
        import logging
        _logger = logging.getLogger("fhir4ds.loader")
        path = Path(path) if not isinstance(path, Path) else path

        if not path.exists():
            raise FileNotFoundError(
                f"Directory not found: {path}"
            )
        if not path.is_dir():
            raise NotADirectoryError(
                f"Not a directory: {path}"
            )

        if extensions is None:
            extensions = [".json", ".ndjson"]

        total = 0
        pattern = "**/*" if recursive else "*"

        for file_path in path.glob(pattern):
            if file_path.is_file() and file_path.suffix in extensions:
                try:
                    if file_path.suffix == ".ndjson":
                        total += self.load_ndjson(file_path, strict=False)
                    else:
                        total += self.load_file(file_path)
                except (json.JSONDecodeError, TypeError, ValueError, KeyError) as e:
                    _logger.warning("Skipping non-FHIR file %s: %s", file_path, e)

        return total

    def load_from_url(self, url: str, headers: Optional[dict] = None) -> int:
        """
        Load from a FHIR server URL.

        Returns the number of resources loaded.
        """
        import urllib.request

        if not isinstance(url, str) or not url:
            raise ValueError("url must be a non-empty string")
        scheme = urlparse(url).scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError(
                f"Unsupported URL scheme {scheme!r}. Only 'http' and 'https' are allowed."
            )
        if headers is not None and not isinstance(headers, dict):
            raise TypeError(f"headers must be a dict if provided, got {type(headers).__name__}")

        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        if not isinstance(data, dict):
            raise TypeError(
                "FHIR server response must contain an object resource or Bundle, "
                f"got {type(data).__name__}"
            )
        if data.get("resourceType") == "Bundle":
            return self.load_bundle(data)
        else:
            self.load_resource(data)
            return 1

    def clear(self) -> None:
        """Clear all resources from the table."""
        self.con.execute(f"DELETE FROM {self._quoted_table_name}")

    def count(self, resource_type: Optional[str] = None) -> int:
        """Count resources in the table, optionally filtered by type."""
        if resource_type:
            result = self.con.execute(
                f"SELECT COUNT(*) FROM {self._quoted_table_name} WHERE resourceType = ?",
                [resource_type]
            ).fetchone()
        else:
            result = self.con.execute(
                f"SELECT COUNT(*) FROM {self._quoted_table_name}"
            ).fetchone()
        return result[0] if result else 0

    def load_valuesets(
        self,
        valuesets: List[Any],
        table_name: str = "valueset_codes"
    ) -> int:
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(
                f"table_name must be a valid SQL identifier, got {table_name!r}"
            )
        quoted_table_name = quote_identifier(table_name)
        """
        Load ValueSet codes into a table for fhirpath_in_valueset UDF.

        Creates a table with columns:
        - valueset_url VARCHAR
        - system VARCHAR
        - code VARCHAR
        - display VARCHAR

        This table is queried by the fhirpath_in_valueset UDF to check
        if a code is in a valueset without making API calls.

        Args:
            valuesets: List of ResolvedValueSet objects from DependencyResolver,
                      or list of dicts with 'url' and 'codes' keys.
                      Each code should have 'system', 'code', and optionally 'display'.
            table_name: Name of the table to create/populate

        Returns:
            Total number of codes loaded
        """
        if valuesets is None:
            raise TypeError("valuesets must be a list, got None")
        if not isinstance(valuesets, list):
            raise TypeError(f"valuesets must be a list, got {type(valuesets).__name__}")

        # Create table if not exists
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS {quoted_table_name} (
                valueset_url VARCHAR,
                system VARCHAR,
                code VARCHAR,
                display VARCHAR
            )
        """)

        total_codes = 0
        valueset_urls = []
        systems = []
        code_values = []
        displays = []
        for index, vs in enumerate(valuesets):
            if vs is None:
                raise TypeError(f"valuesets[{index}] must be a ValueSet object or dict, got None")
            # Handle both object with .url/.codes attributes and dict with 'url'/'codes' keys
            if hasattr(vs, 'url'):
                vs_url = vs.url
                codes = vs.codes
            elif isinstance(vs, dict):
                vs_url = vs.get("url")
                codes = vs.get("codes")
                if codes is None and vs.get("resourceType") == "ValueSet":
                    codes = _extract_codes_from_valueset_resource(vs)
                if codes is None:
                    codes = []
            else:
                raise TypeError(
                    f"valuesets[{index}] must be a ValueSet object or dict, "
                    f"got {type(vs).__name__}"
                )
            if not isinstance(vs_url, str) or not vs_url:
                raise ValueError(f"valuesets[{index}] must include a non-empty string 'url'")
            if not isinstance(codes, list):
                raise TypeError(f"valuesets[{index}].codes must be a list, got {type(codes).__name__}")

            for code_index, code_entry in enumerate(codes):
                if code_entry is None:
                    raise TypeError(
                        f"valuesets[{index}].codes[{code_index}] must be a code object or dict, got None"
                    )
                # Handle both object and dict for code entries
                if hasattr(code_entry, 'system'):
                    system = code_entry.system
                    code = code_entry.code
                    display = getattr(code_entry, 'display', None)
                elif isinstance(code_entry, dict):
                    system = code_entry.get("system")
                    code = code_entry.get("code")
                    display = code_entry.get("display")
                else:
                    raise TypeError(
                        f"valuesets[{index}].codes[{code_index}] must be a code object or dict, "
                        f"got {type(code_entry).__name__}"
                    )
                if not isinstance(system, str) or not isinstance(code, str):
                    raise ValueError(
                        f"valuesets[{index}].codes[{code_index}] must include string "
                        "'system' and 'code' values"
                    )

                valueset_urls.append(vs_url)
                systems.append(system)
                code_values.append(code)
                displays.append(display)
                total_codes += 1

        if valueset_urls:
            try:
                import pyarrow as pa

                arrow_table = pa.table({
                    "valueset_url": pa.array(valueset_urls, type=pa.string()),
                    "system": pa.array(systems, type=pa.string()),
                    "code": pa.array(code_values, type=pa.string()),
                    "display": pa.array(displays, type=pa.string()),
                })
                temp_name = f"_{table_name}_bulk_valuesets"
                quoted_temp_name = quote_identifier(temp_name)
                self.con.register(temp_name, arrow_table)
                try:
                    self.con.execute(
                        f"INSERT INTO {quoted_table_name} "
                        f"SELECT valueset_url, system, code, display "
                        f"FROM {quoted_temp_name}"
                    )
                finally:
                    self.con.unregister(temp_name)
            except ImportError:
                rows = list(zip(valueset_urls, systems, code_values, displays))
                self.con.executemany(
                    f"INSERT INTO {quoted_table_name} VALUES (?, ?, ?, ?)",
                    rows,
                )

        # Create index for fast lookups after bulk insert so fresh loads do
        # not maintain the index one row at a time.
        quoted_index_name = quote_identifier(f"idx_{table_name}_lookup")
        self.con.execute(f"""
            CREATE INDEX IF NOT EXISTS {quoted_index_name}
            ON {quoted_table_name} (valueset_url, system, code)
        """)

        self._refresh_in_valueset_udf(table_name)
        return total_codes

    def count_valueset_codes(
        self,
        valueset_url: Optional[str] = None,
        table_name: str = "valueset_codes"
    ) -> int:
        """
        Count codes in the valueset_codes table, optionally filtered by valueset URL.

        Args:
            valueset_url: Optional URL to filter by
            table_name: Name of the valueset codes table

        Returns:
            Number of codes matching the filter
        """
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(
                f"table_name must be a valid SQL identifier, got {table_name!r}"
            )
        quoted_table_name = quote_identifier(table_name)
        if not self.valueset_table_exists(table_name):
            return 0
        if valueset_url:
            result = self.con.execute(
                f"SELECT COUNT(*) FROM {quoted_table_name} WHERE valueset_url = ?",
                [valueset_url]
            ).fetchone()
        else:
            result = self.con.execute(
                f"SELECT COUNT(*) FROM {quoted_table_name}"
            ).fetchone()
        return result[0] if result else 0

    def clear_valuesets(self, table_name: str = "valueset_codes") -> None:
        """
        Clear all codes from the valueset_codes table.

        Args:
            table_name: Name of the valueset codes table
        """
        if not isinstance(table_name, str) or not table_name.isidentifier():
            raise ValueError(
                f"table_name must be a valid SQL identifier, got {table_name!r}"
            )
        quoted_table_name = quote_identifier(table_name)
        if not self.valueset_table_exists(table_name):
            return
        self.con.execute(f"DELETE FROM {quoted_table_name}")
        self._refresh_in_valueset_udf(table_name)

    def valueset_table_exists(self, table_name: str = "valueset_codes") -> bool:
        """
        Check if the valueset codes table exists.

        Args:
            table_name: Name of the valueset codes table to check

        Returns:
            True if the table exists, False otherwise
        """
        result = self.con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
            [table_name]
        ).fetchone()
        return result is not None

    def _refresh_in_valueset_udf(self, table_name: str = "valueset_codes") -> None:
        """Refresh the in_valueset Python UDF cache from the populated valueset_codes table.

        When duckdb_cql_py registers ``in_valueset``, it uses an empty in-memory
        cache.  After codes are loaded into the SQL table we must rebuild the cache
        so that subsequent ``in_valueset()`` calls return correct results.

        Uses a soft import of ``duckdb_cql_py`` so that ``cql-py`` does not gain a
        hard dependency on the higher-level package.
        """
        if self._refresh_cpp_in_valueset_cache(table_name):
            return
        quoted_table_name = quote_identifier(table_name)

        try:
            from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf
        except ImportError:
            return

        try:
            rows = self.con.execute(
                f"SELECT valueset_url, system, code FROM {quoted_table_name}"
            ).fetchall()
        except (duckdb.CatalogException, duckdb.BinderException) if duckdb else () as e:
            _logger.warning("Failed to query valueset table '%s': %s", table_name, e)
            return
        except Exception as e:
            _logger.error("Unexpected error querying valueset table '%s': %s", table_name, e)
            raise

        # Update the instance-level cache dict IN-PLACE so the already-registered
        # UDF closure sees the new values without requiring re-registration.
        self._valueset_udf_cache.clear()
        for vs_url, system, code in rows:
            # Normalize system identifiers (OID → URL, SNOMED module → base)
            from fhir4ds.cql.duckdb.udf.system_resolver import SystemResolver
            norm_sys = SystemResolver.normalize(system) if system else ""
            self._valueset_udf_cache.setdefault(vs_url, set()).add((norm_sys, code or ""))

        try:
            # Register the Python UDF once per connection. Its closure references
            # the shared cache dict above, so future refreshes only need to update
            # that dict in-place and recreate the macros.
            if self.con not in _VALUESET_UDF_REGISTERED_CONNECTIONS:
                udf_func = createValuesetMembershipUdf(self._valueset_udf_cache)
                self.con.create_function("_in_valueset_python", udf_func, null_handling="special")
                with _CACHE_LOCK:
                    _VALUESET_UDF_REGISTERED_CONNECTIONS.add(self.con)
            self.con.execute(
                "CREATE OR REPLACE MACRO in_valueset(res, path, vs_url) AS "
                "_in_valueset_python(res, path, vs_url)"
            )
            self.con.execute(
                "CREATE OR REPLACE MACRO fhirpath_in_valueset(res, path, vs_url) AS "
                "_in_valueset_python(res, path, vs_url)"
            )
        except (duckdb.CatalogException, duckdb.InvalidInputException) if duckdb else () as e:
            _logger.warning("Failed to refresh valueset UDF macros: %s", e)
        except Exception as e:
            _logger.error("Unexpected error refreshing valueset UDF macros: %s", e)
            raise

    def _refresh_cpp_in_valueset_cache(self, table_name: str = "valueset_codes") -> bool:
        """Populate the native CQL valueset cache when the C++ extension exposes it."""
        import os
        use_native = os.environ.get("FHIR4DS_USE_CPP_VALUESET_CACHE", "").lower()
        if use_native in ("0", "false", "no", "off"):
            return False
        quoted_table_name = quote_identifier(table_name)

        try:
            self.con.execute("SELECT cql_valueset_cache_clear()").fetchone()
        except Exception:
            return False

        try:
            self.con.execute(
                f"SELECT cql_valueset_cache_add(valueset_url, system, code) "
                f"FROM {quoted_table_name}"
            ).fetchall()
            # Remove stale Python macros from prior refreshes so SQL resolves to
            # the native in_valueset function. Keep the fhirpath_* alias as a macro.
            for macro_name in ("in_valueset", "fhirpath_in_valueset"):
                try:
                    self.con.execute(f"DROP MACRO IF EXISTS {macro_name}")
                except Exception:
                    pass
            self.con.execute(
                "CREATE OR REPLACE MACRO fhirpath_in_valueset(res, path, vs_url) AS "
                "in_valueset(res, path, vs_url)"
            )
            return True
        except Exception as e:
            _logger.warning("Failed to populate C++ valueset cache; using Python UDF: %s", e)
            return False
