# src/cql_py/loader/fhir_loader.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Union, List, Optional, Any
from weakref import WeakKeyDictionary, WeakSet
try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

_logger = logging.getLogger(__name__)

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
        self.con = con
        self.table_name = table_name
        # Share one mutable cache per DuckDB connection so repeated FHIRDataLoader
        # instances update the same _in_valueset_python closure in-place.
        shared_cache = _VALUESET_UDF_CACHE_BY_CONNECTION.get(con)
        if shared_cache is None:
            shared_cache = {}
            _VALUESET_UDF_CACHE_BY_CONNECTION[con] = shared_cache
        self._valueset_udf_cache: dict = shared_cache
        if create_table:
            self._create_table()

    def _create_table(self) -> None:
        """Create the resources table if it doesn't exist."""
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id VARCHAR,
                resourceType VARCHAR,
                resource JSON,
                patient_ref VARCHAR
            )
        """)

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
                    if "/" in reference:
                        return reference.split("/")[-1]
                    return reference

        return None

    def load_resource(self, resource: dict) -> None:
        """Load a single FHIR resource."""
        patient_ref = self._extract_patient_ref(resource)
        self.con.execute(
            f"INSERT INTO {self.table_name} VALUES (?, ?, ?, ?)",
            [
                resource.get("id"),
                resource.get("resourceType"),
                json.dumps(resource),
                patient_ref,
            ]
        )

    def load_bundle(self, bundle: dict) -> int:
        """
        Load all resources from a FHIR Bundle.

        Returns the number of resources loaded.
        """
        if bundle.get("resourceType") != "Bundle":
            raise ValueError("Expected a FHIR Bundle resource")

        count = 0
        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if resource:
                self.load_resource(resource)
                count += 1

        return count

    def load_file(self, path: Path) -> int:
        """
        Load from a JSON file.

        Automatically detects if it's a Bundle or single resource.
        Returns the number of resources loaded.
        """
        data = json.loads(path.read_text())
        resource_type = data.get("resourceType")

        if resource_type == "Bundle":
            return self.load_bundle(data)
        else:
            self.load_resource(data)
            return 1

    def load_ndjson(self, path: Path) -> int:
        """
        Load from an NDJSON file (one resource per line).

        Returns the number of resources loaded.
        """
        count = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    resource = json.loads(line)
                    self.load_resource(resource)
                    count += 1
        return count

    def load_directory(
        self,
        path: Path,
        recursive: bool = True,
        extensions: List[str] = None
    ) -> int:
        """
        Load all supported files from a directory.

        Returns the total number of resources loaded.
        """
        if extensions is None:
            extensions = [".json", ".ndjson"]

        total = 0
        pattern = "**/*" if recursive else "*"

        for file_path in path.glob(pattern):
            if file_path.is_file() and file_path.suffix in extensions:
                if file_path.suffix == ".ndjson":
                    total += self.load_ndjson(file_path)
                else:
                    total += self.load_file(file_path)

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
        except Exception as e:
            _logger.warning("Failed to query valueset table '%s': %s", table_name, e)
            return

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
                _VALUESET_UDF_REGISTERED_CONNECTIONS.add(self.con)
            self.con.execute(
                "CREATE OR REPLACE MACRO in_valueset(res, path, vs_url) AS "
                "_in_valueset_python(res, path, vs_url)"
            )
            self.con.execute(
                "CREATE OR REPLACE MACRO fhirpath_in_valueset(res, path, vs_url) AS "
                "_in_valueset_python(res, path, vs_url)"
            )
        except Exception as e:
            _logger.warning("Failed to refresh valueset UDF macros: %s", e)
