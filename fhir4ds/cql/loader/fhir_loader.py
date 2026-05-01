# src/cql_py/loader/fhir_loader.py
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Union, List, Optional, Any
from weakref import WeakKeyDictionary, WeakSet
try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

_logger = logging.getLogger(__name__)

# Per-connection caches. WeakKeyDictionary ensures entries are cleaned up
# when DuckDB connections are garbage-collected.  Protected by a lock for
# thread safety when multiple threads register UDFs on different connections.
_CACHE_LOCK = threading.Lock()
_VALUESET_UDF_CACHE_BY_CONNECTION = WeakKeyDictionary()
_VALUESET_UDF_REGISTERED_CONNECTIONS = WeakSet()


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
    ):
        if con is None:
            raise TypeError("Expected a DuckDB connection for 'con', got None")
        if not isinstance(con, duckdb.DuckDBPyConnection):
            raise TypeError(
                f"Expected a DuckDB connection for 'con', got {type(con).__name__}"
            )
        self.con = con
        self.table_name = table_name
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
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
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
        to look up the referenced resource by ``ResourceType/id`` or by a
        JSON Reference object ``{"reference": "ResourceType/id"}``.
        """
        tbl = self.table_name
        try:
            self.con.execute(f"""
                CREATE OR REPLACE MACRO resolve(ref) AS (
                    SELECT r.resource FROM {tbl} r
                    WHERE ref IS NOT NULL
                    AND r.id = split_part(
                        CASE WHEN ref LIKE '{{%'
                             THEN json_extract_string(ref::VARCHAR, '$.reference')
                             ELSE ref
                        END, '/', -1
                    )
                    AND r.resourceType = split_part(
                        CASE WHEN ref LIKE '{{%'
                             THEN json_extract_string(ref::VARCHAR, '$.reference')
                             ELSE ref
                        END, '/', 1
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
        resource_id = resource.get("id")
        if resource_id is not None and not isinstance(resource_id, str):
            raise ValueError(
                f"Resource 'id' must be a string per FHIR R4 spec, "
                f"got {type(resource_id).__name__}: {resource_id!r}"
            )
        patient_ref = self._extract_patient_ref(resource)
        resource_json = json.dumps(resource)

        if resource_id is not None and resource_type is not None:
            # Delete existing resource with same identity, then insert
            self.con.execute(
                f"DELETE FROM {self.table_name} WHERE id = ? AND resourceType = ?",
                [resource_id, resource_type],
            )
        self.con.execute(
            f"INSERT INTO {self.table_name} VALUES (?, ?, ?, ?)",
            [resource_id, resource_type, resource_json, patient_ref],
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
        if not resources:
            return 0

        # Build rows and deduplicate: last-write-wins for same (id, resourceType)
        seen: dict[tuple[str, str], int] = {}
        rows: list[tuple] = []
        dedup_count = 0
        for resource in resources:
            if not isinstance(resource, dict):
                raise TypeError(f"Expected dict, got {type(resource).__name__}")
            resource_type = resource.get("resourceType")
            if not resource_type or not isinstance(resource_type, str):
                raise ValueError(
                    f"Resource must have a string 'resourceType' field. "
                    f"Got: {resource_type!r}"
                )
            resource_id = resource.get("id")
            patient_ref = self._extract_patient_ref(resource)
            resource_json = json.dumps(resource)
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
                f"DELETE FROM {self.table_name} WHERE id = ? AND resourceType = ?",
                dedup_keys,
            )

        # Batch insert
        self.con.executemany(
            f"INSERT INTO {self.table_name} VALUES (?, ?, ?, ?)",
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

        resources = []
        for entry in bundle.get("entry") or []:
            if entry is None:
                continue
            resource = entry.get("resource")
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
                        resources.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        if strict:
                            raise ValueError(
                                f"Malformed JSON at line {line_num} in {path}: {e}"
                            ) from e
                        _logger.warning(
                            "Skipping malformed JSON at line %d in %s: %s",
                            line_num, path, e,
                        )
        for resource in resources:
            self.load_resource(resource)
        return len(resources)

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
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    _logger.warning("Skipping non-FHIR file %s: %s", file_path, e)

        return total

    def load_from_url(self, url: str, headers: Optional[dict] = None) -> int:
        """
        Load from a FHIR server URL.

        Returns the number of resources loaded.
        """
        import urllib.request

        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        if data.get("resourceType") == "Bundle":
            return self.load_bundle(data)
        else:
            self.load_resource(data)
            return 1

    def clear(self) -> None:
        """Clear all resources from the table."""
        self.con.execute(f"DELETE FROM {self.table_name}")

    def count(self, resource_type: Optional[str] = None) -> int:
        """Count resources in the table, optionally filtered by type."""
        if resource_type:
            result = self.con.execute(
                f"SELECT COUNT(*) FROM {self.table_name} WHERE resourceType = ?",
                [resource_type]
            ).fetchone()
        else:
            result = self.con.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()
        return result[0] if result else 0

    def load_valuesets(
        self,
        valuesets: List[Any],
        table_name: str = "valueset_codes"
    ) -> int:
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
        # Create table if not exists
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                valueset_url VARCHAR,
                system VARCHAR,
                code VARCHAR,
                display VARCHAR
            )
        """)

        # Create index for fast lookups
        self.con.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_lookup
            ON {table_name} (valueset_url, system, code)
        """)

        total_codes = 0
        for vs in valuesets:
            # Handle both object with .url/.codes attributes and dict with 'url'/'codes' keys
            if hasattr(vs, 'url'):
                vs_url = vs.url
                codes = vs.codes
            else:
                vs_url = vs.get("url")
                codes = vs.get("codes", [])

            for code_entry in codes:
                # Handle both object and dict for code entries
                if hasattr(code_entry, 'system'):
                    system = code_entry.system
                    code = code_entry.code
                    display = getattr(code_entry, 'display', None)
                else:
                    system = code_entry.get("system")
                    code = code_entry.get("code")
                    display = code_entry.get("display")

                self.con.execute(
                    f"INSERT INTO {table_name} VALUES (?, ?, ?, ?)",
                    [vs_url, system, code, display]
                )
                total_codes += 1

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
        if valueset_url:
            result = self.con.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE valueset_url = ?",
                [valueset_url]
            ).fetchone()
        else:
            result = self.con.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()
        return result[0] if result else 0

    def clear_valuesets(self, table_name: str = "valueset_codes") -> None:
        """
        Clear all codes from the valueset_codes table.

        Args:
            table_name: Name of the valueset codes table
        """
        self.con.execute(f"DELETE FROM {table_name}")
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
        try:
            from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf
        except ImportError:
            return

        try:
            rows = self.con.execute(
                f"SELECT valueset_url, system, code FROM {table_name}"
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
