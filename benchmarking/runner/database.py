"""
Database initialization and data loading.
"""
import duckdb
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

def _fix_claim_encounter_refs(
    claim: dict, encounter_ids: set,
) -> dict:
    """Fix Claim item.encounter references that don't match any bundle encounter.

    eCQM test fixtures sometimes have Claim.item.encounter pointing to a
    template/dummy encounter ID that doesn't exist in the bundle.  When
    there is exactly one encounter in the bundle that is NOT already
    referenced by any item, we rewrite the dangling references to point to
    that encounter so ``claimDiagnosis()`` / ``claim_principal_diagnosis``
    can match them.
    """
    items = claim.get("item", [])
    if not items:
        return claim

    # Collect all encounter refs currently used by items
    dangling_items: list[int] = []
    for idx, item in enumerate(items):
        for enc_ref in item.get("encounter", []):
            ref_str = enc_ref.get("reference", "")
            ref_id = ref_str.rsplit("/", 1)[-1] if "/" in ref_str else ref_str
            if ref_id not in encounter_ids:
                dangling_items.append(idx)
                break

    if not dangling_items:
        return claim

    # Rewrite dangling refs.  When only one encounter exists, use it.
    # When multiple encounters exist, link each dangling item to ALL
    # bundle encounters so that claimDiagnosis() can match any of them
    # (the CQL join will filter to the correct encounter at query time).
    if encounter_ids:
        modified = dict(claim)
        modified["item"] = [dict(it) for it in items]
        for idx in dangling_items:
            modified["item"][idx]["encounter"] = [
                {"reference": f"Encounter/{eid}"} for eid in encounter_ids
            ]
        return modified

    return claim


class BenchmarkDatabase:
    """
    Manages DuckDB connection with pre-loaded data.
    """

    def __init__(self, db_path: str = ":memory:"):
        # Enable loading unsigned extensions before connecting
        self.conn = duckdb.connect(db_path, config={'allow_unsigned_extensions': 'true'})
        self._setup_timings: Dict[str, float] = {}

        # CQL semantics use singleton promotion/demotion, so scalar subqueries
        # may legitimately return multiple rows in certain patterns
        self.conn.execute("SET scalar_subquery_error_on_multiple_rows=false")

        # Paths to C++ extensions
        workspace_root = Path(__file__).parent.parent.parent.absolute()
        
        # Try both build directory and bundled package locations
        fhirpath_cpp_candidates = [
            workspace_root / "extensions" / "fhirpath" / "build" / "release" / "extension" / "fhirpath" / "fhirpath.duckdb_extension",
            workspace_root / "fhir4ds" / "fhirpath" / "duckdb" / "extensions" / "fhirpath.duckdb_extension",
        ]
        cql_cpp_candidates = [
            workspace_root / "extensions" / "cql" / "build" / "release" / "extension" / "cql" / "cql.duckdb_extension",
            workspace_root / "fhir4ds" / "cql" / "duckdb" / "extensions" / "cql.duckdb_extension",
        ]

        fhirpath_cpp = next((p for p in fhirpath_cpp_candidates if p.exists()), None)
        cql_cpp = next((p for p in cql_cpp_candidates if p.exists()), None)

        use_cpp = os.environ.get("USE_CPP_EXTENSIONS", "1").lower() in ("1", "true", "yes")
        loaded_cpp = False
        
        if use_cpp and fhirpath_cpp and cql_cpp:
            try:
                # On WSL2, loading .duckdb_extension binaries directly from the Windows
                # NTFS filesystem (/mnt/d/) is unreliable (non-deterministic results due
                # to memory-mapped I/O over the plan 9 filesystem driver). Copy to the
                # Linux tmpfs first for stable loading.
                import shutil
                import tempfile
                _ext_tmp = Path(tempfile.gettempdir()) / "duckdb_cpp_ext"
                _ext_tmp.mkdir(exist_ok=True)
                fhirpath_load = _ext_tmp / "fhirpath.duckdb_extension"
                cql_load = _ext_tmp / "cql.duckdb_extension"
                # Only copy if source is newer (avoids redundant copies on repeated runs)
                if not fhirpath_load.exists() or fhirpath_cpp.stat().st_mtime > fhirpath_load.stat().st_mtime:
                    shutil.copy2(str(fhirpath_cpp), str(fhirpath_load))
                if not cql_load.exists() or cql_cpp.stat().st_mtime > cql_load.stat().st_mtime:
                    shutil.copy2(str(cql_cpp), str(cql_load))
                self.conn.execute(f"LOAD '{fhirpath_load}'")
                self.conn.execute(f"LOAD '{cql_load}'")
                # Add aliases for compatibility with Python-style naming if needed
                try:
                    self.conn.execute("CREATE OR REPLACE MACRO fhirpath_udf(res, expr) AS fhirpath(res, expr)")
                except Exception as e:
                    print(f"  Warning: Failed to create fhirpath_udf macro: {e}")
                
                # We need to make sure 'fhirpath' used by Python UDFs (like in_valueset)
                # resolves to the one we want. When C++ is loaded, 'fhirpath' is native.
                loaded_cpp = True
                print("  Loaded C++ native extensions (fhirpath, cql)")
            except Exception as e:
                print(f"  Warning: Failed to load C++ extensions: {e}")

        # Always try to register unified fhir4ds UDFs (they handle fallback correctly)
        try:
            import fhir4ds
            fhir4ds.register(self.conn)
        except ImportError:
            if not loaded_cpp:
                # Try to register UDFs if available via legacy internal paths
                try:
                    from fhir4ds.cql.duckdb import register as register_cql_udfs
                    register_cql_udfs(self.conn)
                except ImportError:
                    try:
                        from fhir4ds.fhirpath.duckdb import register_fhirpath
                        register_fhirpath(self.conn)
                    except ImportError:
                        pass

        # Audit macros must always be registered regardless of whether the C++ extension
        # or Python UDFs provide fhirpath. The C++ CQL extension doesn't include them.
        try:
            from fhir4ds.cql.duckdb.macros.audit import register_audit_macros
            register_audit_macros(self.conn)
        except ImportError:
            pass

    def scope_to_measure(self, measure_id: str) -> None:
        """Scope the ``resources`` table to a single measure's test data.

        When multiple measures share patient IDs but have different test
        resources, we must isolate each measure's data during evaluation.
        This replaces the ``resources`` view with one filtered to only
        the rows loaded from *measure_id*'s bundles.
        """
        try:
            self.conn.execute("SELECT source_measure FROM _resources_all LIMIT 0")
        except Exception:
            return  # no source_measure column – nothing to scope
        # Sanitize measure_id (alphanumeric + limited punctuation only)
        safe_id = "".join(c for c in measure_id if c.isalnum() or c in "-_")
        self.conn.execute("DROP VIEW IF EXISTS resources")
        self.conn.execute(
            f"CREATE VIEW resources AS "
            f"SELECT id, resourceType, resource, patient_ref "
            f"FROM _resources_all "
            f"WHERE source_measure = '{safe_id}'"
        )

    def unscope_resources(self) -> None:
        """Remove measure scoping — expose all loaded resources."""
        try:
            self.conn.execute("SELECT 1 FROM _resources_all LIMIT 0")
        except Exception:
            return
        self.conn.execute("DROP VIEW IF EXISTS resources")
        self.conn.execute(
            "CREATE VIEW resources AS "
            "SELECT id, resourceType, resource, patient_ref "
            "FROM _resources_all"
        )

    def load_all_test_data(self, measure_configs: List["MeasureConfig"]) -> Dict[str, Any]:
        """Load ALL test patients from ALL measures into the database."""
        import json as _json
        start = time.perf_counter()
        total_patients = 0
        total_resources = 0

        # Try to use FHIRDataLoader if available
        try:
            from fhir4ds.cql import FHIRDataLoader
            loader = FHIRDataLoader(self.conn)

            # Add source_measure column for per-measure scoping
            self.conn.execute(
                f"ALTER TABLE {loader.table_name} ADD COLUMN IF NOT EXISTS source_measure VARCHAR"
            )

            for config in measure_configs:
                bundle_files = list(config.test_dir.glob("tests-*-bundle.json"))
                if bundle_files:
                    # Strategy A: Bundle files (2025 format)
                    for bundle_path in bundle_files:
                        try:
                            bundle = _json.loads(bundle_path.read_text())
                            entries = bundle.get("entry", [])
                            all_resources = []
                            for e in entries:
                                res = e.get("resource", {})
                                rt = res.get("resourceType")
                                if rt == "Bundle":
                                    for ie in res.get("entry", []):
                                        ir = ie.get("resource", {})
                                        if ir.get("resourceType"):
                                            all_resources.append(ir)
                                elif rt:
                                    all_resources.append(res)
                            seen_json: set = set()
                            unique_resources = []
                            for res in all_resources:
                                key = _json.dumps(res, sort_keys=True)
                                if key not in seen_json:
                                    seen_json.add(key)
                                    unique_resources.append(res)
                            patient_id = None
                            encounter_ids: set = set()
                            for res in unique_resources:
                                if res.get("resourceType") == "Patient":
                                    patient_id = res.get("id")
                                elif res.get("resourceType") == "Encounter":
                                    eid = res.get("id")
                                    if eid:
                                        encounter_ids.add(eid)
                            for res in unique_resources:
                                rt = res.get("resourceType")
                                if not rt:
                                    continue
                                if rt == "Claim" and encounter_ids:
                                    res = _fix_claim_encounter_refs(res, encounter_ids)
                                ref = loader._extract_patient_ref(res)
                                if patient_id and rt != "Patient" and rt not in (
                                    "MeasureReport", "Bundle", "Organization",
                                    "Practitioner", "PractitionerRole",
                                ):
                                    ref = patient_id
                                loader.con.execute(
                                    f"INSERT INTO {loader.table_name} VALUES (?, ?, ?, ?, ?)",
                                    [res.get("id"), rt, _json.dumps(res), ref, config.id],
                                )
                                total_resources += 1
                        except Exception as e:
                            print(f"Warning: Failed to load {bundle_path}: {e}")
                else:
                    # Strategy B: Directory-based (2026 format)
                    for subdir in sorted(config.test_dir.iterdir()):
                        if not subdir.is_dir():
                            continue
                        try:
                            patient_id = None
                            encounter_ids: set = set()
                            resources_in_dir = []
                            for json_file in sorted(subdir.glob("*.json")):
                                try:
                                    res = _json.loads(json_file.read_text())
                                except (_json.JSONDecodeError, OSError):
                                    continue
                                rt = res.get("resourceType")
                                if not rt:
                                    continue
                                if rt == "Patient":
                                    patient_id = res.get("id")
                                elif rt == "Encounter":
                                    eid = res.get("id")
                                    if eid:
                                        encounter_ids.add(eid)
                                resources_in_dir.append(res)
                            for res in resources_in_dir:
                                rt = res.get("resourceType")
                                if not rt:
                                    continue
                                if rt == "Claim" and encounter_ids:
                                    res = _fix_claim_encounter_refs(res, encounter_ids)
                                ref = loader._extract_patient_ref(res)
                                if patient_id and rt != "Patient" and rt not in (
                                    "MeasureReport", "Bundle", "Organization",
                                    "Practitioner", "PractitionerRole",
                                ):
                                    ref = patient_id
                                loader.con.execute(
                                    f"INSERT INTO {loader.table_name} VALUES (?, ?, ?, ?, ?)",
                                    [res.get("id"), rt, _json.dumps(res), ref, config.id],
                                )
                                total_resources += 1
                        except Exception as e:
                            print(f"Warning: Failed to load {subdir.name}: {e}")
        except ImportError:
            # Fallback: load JSON directly
            for config in measure_configs:
                for bundle_path in config.test_dir.glob("tests-*-bundle.json"):
                    with open(bundle_path) as f:
                        bundle = _json.load(f)
                    for entry in bundle.get("entry", []):
                        resource = entry.get("resource", {})
                        total_resources += 1

        self._setup_timings["data_load"] = time.perf_counter() - start

        # Rename the raw table and expose a view so scope_to_measure()
        # can swap it for a filtered version during --all runs.
        try:
            self.conn.execute("SELECT source_measure FROM resources LIMIT 0")
            has_source = True
        except Exception:
            has_source = False

        if has_source:
            self.conn.execute("ALTER TABLE resources RENAME TO _resources_all")
            self.conn.execute(
                "CREATE VIEW resources AS "
                "SELECT id, resourceType, resource, patient_ref "
                "FROM _resources_all"
            )

        # Try to get patient count
        try:
            result = self.conn.execute(
                "SELECT COUNT(DISTINCT patient_ref) FROM resources"
            ).fetchone()
            total_patients = result[0] if result else 0
        except:
            total_patients = total_resources  # Fallback

        return {
            "load_time_s": self._setup_timings["data_load"],
            "total_patients": total_patients,
            "total_resources": total_resources,
        }

    def load_all_valuesets(self, valueset_paths: List[Path]) -> Dict[str, Any]:
        """Load ALL valuesets into valueset_codes table."""
        import json as _json
        start = time.perf_counter()
        total_valuesets = 0
        total_codes = 0

        try:
            from fhir4ds.cql import FHIRDataLoader
            loader = FHIRDataLoader(self.conn)

            def _parse_valueset_file(path: Path):
                """Parse a FHIR ValueSet JSON file into a dict for load_valuesets."""
                with open(path) as f:
                    vs = _json.load(f)
                # Handle FHIR Bundle containing ValueSet resources
                if vs.get("resourceType") == "Bundle":
                    results = []
                    for entry in vs.get("entry", []):
                        r = entry.get("resource", {})
                        if r.get("resourceType") == "ValueSet":
                            parsed = _parse_single_valueset(r)
                            if parsed["codes"]:
                                results.append(parsed)
                    return results
                return [_parse_single_valueset(vs)]

            def _parse_single_valueset(vs):
                """Parse a single ValueSet resource dict."""
                url = vs.get("url", "")
                seen = set()
                codes = []
                vs_includes = []  # compose.include[].valueSet URLs

                def _add(system, code, display):
                    key = (system, code)
                    if key not in seen:
                        seen.add(key)
                        codes.append({"system": system, "code": code, "display": display})

                # Load from expansion
                expansion = vs.get("expansion", {})
                for entry in expansion.get("contains", []):
                    _add(entry.get("system", ""), entry.get("code", ""), entry.get("display", ""))

                expansion_keys = set(seen)  # snapshot before compose merge
                compose_is_null = vs.get("compose") is None

                # Merge explicitly enumerated compose codes when only a few are
                # missing from the expansion (stale expansion that dropped codes
                # added in newer terminology versions).  Skip large deltas —
                # those typically come from 1000-code-capped expansions where the
                # compose is much larger than the intended snapshot.
                compose = vs.get("compose", {})
                compose_extra: list = []
                for inc in compose.get("include", []):
                    system = inc.get("system", "")
                    for concept in inc.get("concept", []):
                        key = (system, concept.get("code", ""))
                        if key not in seen:
                            compose_extra.append((system, concept.get("code", ""), concept.get("display", "")))
                    for vs_url in inc.get("valueSet", []):
                        vs_includes.append(vs_url)
                if len(compose_extra) <= 10:
                    for system, code, display in compose_extra:
                        _add(system, code, display)

                return {
                    "url": url,
                    "codes": codes,
                    "vs_includes": vs_includes,
                    "expansion_keys": expansion_keys,
                    "compose_is_null": compose_is_null,
                }

            # First pass: collect all parsed valuesets
            all_parsed: list = []
            for valueset_path in valueset_paths:
                if valueset_path.is_dir():
                    for vs_file in valueset_path.glob("*.json"):
                        try:
                            all_parsed.extend(_parse_valueset_file(vs_file))
                        except Exception:
                            pass
                elif valueset_path.is_file():
                    try:
                        all_parsed.extend(_parse_valueset_file(valueset_path))
                    except Exception:
                        pass

            # Resolve valueset-includes: when a parent VS includes a child VS
            # and the parent expansion is a subset of the child (thin wrapper),
            # propagate compose-added codes from child to parent.
            url_to_parsed: Dict[str, dict] = {}
            for vs_data in all_parsed:
                url_to_parsed[vs_data["url"]] = vs_data

            for vs_data in all_parsed:
                for inc_url in vs_data.get("vs_includes", []):
                    child = url_to_parsed.get(inc_url)
                    if not child:
                        continue
                    parent_code_set = {c["code"] for c in vs_data["codes"]}
                    child_code_set = {c["code"] for c in child["codes"]}
                    new_codes = child_code_set - parent_code_set
                    # Only propagate if the number of new codes is small
                    # (avoids explosion from large child valuesets)
                    if new_codes and len(new_codes) <= 50:
                        existing = {(c["system"], c["code"]) for c in vs_data["codes"]}
                        for c in child["codes"]:
                            key = (c["system"], c["code"])
                            if key not in existing:
                                vs_data["codes"].append(c)
                                existing.add(key)

            # Propagate compose-merged codes from leaf VSes to grouper VSes.
            # VSAC grouper VSes (compose=null) aggregate leaf VS expansions.
            # When a leaf VS gained codes via compose-merge, the grouper's
            # stale expansion is also missing those codes.  Detect the
            # parent-child relationship by subset containment of expansion
            # codes and propagate the extra codes.
            leaves_with_extra = {}
            for vs_data in all_parsed:
                exp_keys = vs_data.get("expansion_keys", set())
                all_keys = {(c["system"], c["code"]) for c in vs_data["codes"]}
                extra = all_keys - exp_keys
                if extra and exp_keys:
                    leaves_with_extra[vs_data["url"]] = (exp_keys, extra, vs_data)

            if leaves_with_extra:
                grouper_candidates = [
                    vs_data for vs_data in all_parsed
                    if vs_data.get("compose_is_null") and vs_data.get("expansion_keys")
                ]
                for grp in grouper_candidates:
                    grp_exp = grp["expansion_keys"]
                    grp_existing = {(c["system"], c["code"]) for c in grp["codes"]}
                    for leaf_url, (leaf_exp, leaf_extra, leaf_data) in leaves_with_extra.items():
                        if leaf_url == grp["url"]:
                            continue
                        if leaf_exp.issubset(grp_exp):
                            new_codes = leaf_extra - grp_existing
                            if new_codes and len(new_codes) <= 10:
                                for c in leaf_data["codes"]:
                                    key = (c["system"], c["code"])
                                    if key in new_codes:
                                        grp["codes"].append(c)
                                        grp_existing.add(key)

            valuesets_to_load = []
            # Load all into DB
            for vs_data in all_parsed:
                if vs_data["codes"]:
                    valuesets_to_load.append({"url": vs_data["url"], "codes": vs_data["codes"]})

            if valuesets_to_load:
                loader.load_valuesets(valuesets_to_load)

            # Try to get counts
            try:
                result = self.conn.execute(
                    "SELECT COUNT(*) FROM (SELECT DISTINCT valueset_url FROM valueset_codes)"
                ).fetchone()
                total_valuesets = result[0] if result else 0

                result = self.conn.execute(
                    "SELECT COUNT(*) FROM valueset_codes"
                ).fetchone()
                total_codes = result[0] if result else 0
            except Exception:
                pass  # Table may not exist or have different structure

        except Exception as e:
            print(f"Warning: ValueSet loading: {e}")

        self._setup_timings["valueset_load"] = time.perf_counter() - start

        return {
            "load_time_s": self._setup_timings["valueset_load"],
            "total_valuesets": total_valuesets,
            "total_codes": total_codes,
        }

    def get_setup_stats(self) -> Dict[str, Any]:
        """Return initialization statistics."""
        return {
            "timings": self._setup_timings,
            "total_setup_time_s": sum(self._setup_timings.values()),
        }
