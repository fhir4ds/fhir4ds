#!/usr/bin/env python3
"""
Prepare static CMS measure data for wasm-demo.

Reads test cases from ecqm-content-qicore-2025 and outputs static JSON/NDJSON
files to apps/wasm-demo/public/data/ for CMS165 and CMS122.

Also extracts valueset codes and writes pre-translated SQL (from benchmarking
output) with the hardcoded patient-ID filter removed.

Usage:
    python3 scripts/prepare_cms_data.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
BENCHMARKING_DIR = REPO_ROOT / "benchmarking"
ECQM_DIR = BENCHMARKING_DIR / "data" / "ecqm-content-qicore-2025"
VALUESET_DIR = ECQM_DIR / "input" / "vocabulary" / "valueset" / "external"
SUPPLEMENTAL_VALUESET_DIR = BENCHMARKING_DIR / "data" / "valuesets"
TESTS_DIR = ECQM_DIR / "input" / "tests" / "measure"
SQL_OUTPUT_DIR = BENCHMARKING_DIR / "output" / "cql-py" / "sql"

OUT_DIR = Path(__file__).parent.parent / "public" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO_ROOT))

MEASURES = {
    "CMS124": {
        "test_dir_name": "CMS124FHIRCervicalCancerScreening",
        "sql_file": "CMS124.sql",
        "title": "Cervical Cancer Screening",
        "populations": ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"],
    },
    "CMS349": {
        "test_dir_name": "CMS349FHIRHIVScreening",
        "sql_file": "CMS349.sql",
        "title": "HIV Screening",
        "populations": ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"],
    },
    "CMS159": {
        "test_dir_name": "CMS159FHIRDepressionRemissionatTwelveMonths",
        "sql_file": "CMS159.sql",
        "title": "Depression Remission at Twelve Months",
        "populations": ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"],
        # CMS159 full-audit SQL (197KB) is too complex for DuckDB-WASM due to
        # recursive macro inlining depth — use population-only audit instead.
        "use_full_audit": False,
    },
    "CMS74": {
        "test_dir_name": "CMS74FHIRPrimaryCariesPreventionasOfferedbyDentists",
        "sql_file": "CMS74.sql",
        "title": "Primary Caries Prevention as Offered by Dentists",
        "populations": ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"],
    },
    "CMS75": {
        "test_dir_name": "CMS75FHIRChildrenWhoHaveDentalDecayOrCavities",
        "sql_file": "CMS75.sql",
        "title": "Children Who Have Dental Decay or Cavities",
        "populations": ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"],
    },
}


# ─── Valueset extraction ──────────────────────────────────────────────────────

def load_valueset_codes_from_file(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Load (valueset_url → [(system, code)]) from a FHIR ValueSet JSON file."""
    with open(path) as f:
        vs = json.load(f)

    url = vs.get("url", "")
    if not url:
        return {}

    codes: list[tuple[str, str]] = []

    # Prefer expansion.contains (flat list)
    if "expansion" in vs and "contains" in vs["expansion"]:
        for item in vs["expansion"]["contains"]:
            code = item.get("code", "")
            system = item.get("system", "")
            if code:
                codes.append((system, code))

    # Fall back to compose.include
    elif "compose" in vs:
        for include in vs["compose"].get("include", []):
            system = include.get("system", "")
            for concept in include.get("concept", []):
                code = concept.get("code", "")
                if code:
                    codes.append((system, code))

    return {url: codes} if codes else {}


def extract_valuesets_for_sql(sql_text: str) -> dict[str, list[tuple[str, str]]]:
    """Extract codes for all valueset URLs referenced in the SQL."""
    vs_urls = set(re.findall(r"in_valueset\([^,]+,\s*'[^']+',\s*'([^']+)'", sql_text))
    print(f"  Found {len(vs_urls)} unique valueset URLs in SQL")

    all_codes: dict[str, list[tuple[str, str]]] = {}

    # Search in external valueset directory
    vs_dirs = [VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
    for vs_dir in vs_dirs:
        if not vs_dir.exists():
            continue
        for f in vs_dir.rglob("*.json"):
            try:
                result = load_valueset_codes_from_file(f)
                for url, codes in result.items():
                    if url in vs_urls and url not in all_codes:
                        all_codes[url] = codes
            except Exception:
                continue

    missing = vs_urls - set(all_codes.keys())
    if missing:
        print(f"  WARNING: {len(missing)} valuesets not found: {list(missing)[:3]}...")

    print(f"  Loaded codes for {len(all_codes)}/{len(vs_urls)} valuesets")
    return all_codes


# ─── Patient/resource extraction ──────────────────────────────────────────────

def extract_patient_ref(resource: dict, resource_type: str) -> str | None:
    """Extract patient reference from a FHIR resource."""
    ref = None

    if resource_type == "Patient":
        return f"Patient/{resource.get('id', '')}"

    # Standard fields
    for field in ("subject", "patient", "beneficiary"):
        val = resource.get(field)
        if isinstance(val, dict):
            ref = val.get("reference", "")
            break

    if ref and "/" in ref:
        parts = ref.split("/")
        # Normalize to "Patient/<uuid>"
        for i, p in enumerate(parts):
            if p == "Patient" and i + 1 < len(parts):
                return f"Patient/{parts[i + 1]}"
        # Fallback: last UUID-like segment
        return f"Patient/{parts[-1]}"
    elif ref:
        return f"Patient/{ref}"

    return None


SKIP_RESOURCE_TYPES = {"MeasureReport", "Library", "ValueSet", "Measure", "Organization", "Location"}


def load_test_case_resources(patient_dir: Path) -> tuple[list[dict], dict]:
    """Load all FHIR resources from a patient test directory.
    Returns (resources_list, expected_populations).
    """
    resources = []
    expected = {}

    for json_file in patient_dir.iterdir():
        if not json_file.suffix == ".json":
            continue
        try:
            with open(json_file) as f:
                resource = json.load(f)
        except Exception:
            continue

        rt = resource.get("resourceType", "")

        if rt == "MeasureReport":
            for group in resource.get("group", []):
                for pop in group.get("population", []):
                    code_list = pop.get("code", {}).get("coding", [{}])
                    code = code_list[0].get("code", "") if code_list else ""
                    count = pop.get("count", 0)
                    expected[code] = count > 0
            continue

        if rt in SKIP_RESOURCE_TYPES or not rt:
            continue

        resources.append(resource)

    return resources, expected


def extract_resources_for_measure(test_dir_name: str) -> tuple[list[dict], dict[str, dict]]:
    """
    Extract all FHIR resources from test cases.
    Returns (flat_list_with_patient_ref, {patient_id: expected_populations}).
    """
    test_dir = TESTS_DIR / test_dir_name
    flat_resources: list[dict] = []
    expected_by_patient: dict[str, dict] = {}
    seen_resource_ids: set[str] = set()

    patient_dirs = [d for d in sorted(test_dir.iterdir()) if d.is_dir()]
    print(f"  Loading {len(patient_dirs)} test cases...")

    for patient_dir in patient_dirs:
        resources, expected = load_test_case_resources(patient_dir)

        # Find patient ID
        patient_id = patient_dir.name  # UUID directory name
        patient_ref = f"Patient/{patient_id}"

        expected_by_patient[patient_ref] = expected

        for resource in resources:
            rt = resource.get("resourceType", "")
            rid = resource.get("id", "")
            key = f"{rt}/{rid}"

            if key in seen_resource_ids:
                continue
            seen_resource_ids.add(key)

            # Use the test-case directory UUID as patient_ref for all resources.
            # Resources in a test case directory always belong to that patient;
            # some resources (e.g., ServiceRequest) may carry a template patient
            # ID in subject.reference rather than the actual test-case UUID, which
            # would break the patient-resource join in the generated SQL.
            extracted = extract_patient_ref(resource, rt)
            if rt == "Patient":
                ref = extracted or patient_ref
            else:
                ref = patient_ref  # always use test-case UUID for non-Patient resources

            flat_resources.append({
                "id": rid,
                "resourceType": rt,
                "resource": resource,  # raw dict — will be serialized as JSON object in NDJSON
                "patient_ref": ref,
            })

    print(f"  Extracted {len(flat_resources)} unique resources for {len(patient_dirs)} patients")
    return flat_resources, expected_by_patient


# ─── SQL transformation ────────────────────────────────────────────────────────

def strip_patient_id_filter(sql: str) -> str:
    """Remove the hardcoded patient ID IN (...) filter from _patients CTE."""
    return re.sub(
        r"patient_ref IS NOT NULL\s+AND patient_ref IN \([^)]+\)",
        "patient_ref IS NOT NULL",
        sql,
        count=1,
    )


# ── CQL library codesystem aliases → real URIs ─────────────────────────────────
_CODESYSTEM_ALIASES: dict[str, str] = {
    "QICoreCommon.SNOMEDCT": "http://snomed.info/sct",
    "QICoreCommon.LOINC": "http://loinc.org",
    "QICoreCommon.ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm",
    "QICoreCommon.CPT": "http://www.ama-assn.org/go/cpt",
    "QICoreCommon.RXNORM": "http://www.nlm.nih.gov/research/umls/rxnorm",
}


def _translate_fhirpath_bool_where(resource_expr: str, path_expr_raw: str) -> str | None:
    """Translate fhirpath_bool(resource, 'X.coding.where(...).exists()') to SQL."""
    path = path_expr_raw.replace("''", "'")
    m = re.match(r"^(.+)\.where\((.+)\)\.exists\(\)$", path)
    if not m:
        return None
    obj_path, condition = m.group(1), m.group(2)

    sys_and_code = re.match(r"system='([^']+)'\s+and\s+code='([^']+)'", condition)
    code_or_parts = re.findall(r"code='([^']+)'", condition) if not sys_and_code else None

    if sys_and_code:
        system_val = sys_and_code.group(1)
        for alias, uri in _CODESYSTEM_ALIASES.items():
            system_val = system_val.replace(alias, uri)
        code_val = sys_and_code.group(2)
        where_clause = (
            "json_extract_string(c, '$.system') = '{}' AND "
            "json_extract_string(c, '$.code') = '{}'".format(
                system_val.replace("'", "''"), code_val.replace("'", "''")
            )
        )
    elif code_or_parts:
        parts = [
            "json_extract_string(c, '$.code') = '{}'".format(c.replace("'", "''"))
            for c in code_or_parts
        ]
        where_clause = "({})".format(" OR ".join(parts))
    else:
        return None

    if obj_path.startswith("value."):
        coding_path = obj_path[len("value."):]
        from_json_expr = (
            "COALESCE("
            "from_json(json_extract({r}::JSON, '$.valueCodeableConcept.{p}'), '[\"JSON\"]'), "
            "from_json(json_extract({r}::JSON, '$.value.{p}'), '[\"JSON\"]'), "
            "CAST([] AS JSON[]))".format(r=resource_expr, p=coding_path)
        )
    else:
        # Use COALESCE to handle both scalar and array first-level fields.
        # e.g. Encounter.type is CodeableConcept[] so '$.type.coding' is null;
        # we fall back to '$.type[0].coding' automatically.
        first_seg = obj_path.split(".")[0]
        rest = obj_path[len(first_seg):]  # e.g. ".coding"
        from_json_expr = (
            "COALESCE("
            "from_json(json_extract({r}::JSON, '$.{p}'), '[\"JSON\"]'), "
            "from_json(json_extract({r}::JSON, '$.{first}[0]{rest}'), '[\"JSON\"]'), "
            "CAST([] AS JSON[]))".format(r=resource_expr, p=obj_path,
                                         first=first_seg, rest=rest)
        )

    return "EXISTS (SELECT 1 FROM (SELECT unnest({}) AS c) _fbt WHERE {})".format(
        from_json_expr, where_clause
    )


def _translate_fhirpath_text_extension(resource_expr: str, path_expr_raw: str) -> str | None:
    """Translate fhirpath_text(resource, 'extension.where(url=U).field') to SQL."""
    path = path_expr_raw.replace("''", "'")
    m = re.match(r"^extension\.where\(url='([^']+)'\)\.(\w+)$", path)
    if not m:
        return None
    url, field = m.group(1), m.group(2)
    return (
        "(SELECT json_extract_string(e, '$.{f}') "
        "FROM (SELECT unnest(COALESCE(from_json(json_extract({r}::JSON, '$.extension'), "
        "'[\"JSON\"]'), CAST([] AS JSON[]))) AS e) _ext_t "
        "WHERE json_extract_string(e, '$.url') = '{u}' LIMIT 1)"
    ).format(f=field, r=resource_expr, u=url.replace("'", "''"))

def _translate_fhirpath_number_where(resource_expr: str, path_expr_raw: str) -> str | None:
    """Translate fhirpath_number(resource, 'array.where(field = V).result.path') to SQL."""
    path = path_expr_raw.replace("''", "'")
    # Pattern: component.where(code.coding.display = 'X').valueQuantity.value
    m = re.match(r"^(\w+)\.where\(([^=]+)\s*=\s*'([^']+)'\)\.(.+)$", path)
    if not m:
        return None
    arr_field = m.group(1)     # e.g. "component"
    filter_path = m.group(2).strip()  # e.g. "code.coding.display"
    filter_val = m.group(3)    # e.g. "Diastolic blood pressure"
    result_path = m.group(4)   # e.g. "valueQuantity.value"
    val_esc = filter_val.replace("'", "''")
    # Use [0] for nested array access (e.g. code.coding.display → code.coding[0].display)
    # Transform dots in filter_path to use [0] for array nodes
    # Simple heuristic: replace '.display' with '[0].display' for coding arrays
    json_filter_path = filter_path
    if 'coding.' in json_filter_path:
        json_filter_path = json_filter_path.replace('coding.', 'coding[0].')
    return (
        "(SELECT TRY_CAST(json_extract_string(c, '$.{result}') AS DOUBLE) "
        "FROM (SELECT unnest(COALESCE(from_json(json_extract({r}::JSON, '$.{arr}'), "
        "'[\"JSON\"]'), CAST([] AS JSON[]))) AS c) _comp_t "
        "WHERE json_extract_string(c, '$.{fp}') = '{fv}' LIMIT 1)"
    ).format(result=result_path, r=resource_expr, arr=arr_field,
             fp=json_filter_path, fv=val_esc)


def _find_and_replace_fhirpath(sql: str) -> str:
    """Replace complex fhirpath_bool and fhirpath_text calls with SQL equivalents."""
    result: list[str] = []
    i = 0

    while i < len(sql):
        # Find the next fhirpath_bool(, fhirpath_text(, or fhirpath_number( occurrence
        best_pos = len(sql)
        best_fn_str = None
        best_fn_type = None
        for fn_str, fn_type in (
            ("fhirpath_bool(", "bool"),
            ("fhirpath_text(", "text"),
            ("fhirpath_number(", "number"),
        ):
            pos = sql.find(fn_str, i)
            if 0 <= pos < best_pos:
                best_pos, best_fn_str, best_fn_type = pos, fn_str, fn_type

        if best_fn_str is None:
            result.append(sql[i:])
            break

        result.append(sql[i:best_pos])
        open_paren = best_pos + len(best_fn_str) - 1

        # Extract arg1 (resource expression) by tracking paren/string depth
        j = open_paren + 1
        depth = 1
        in_str = False
        arg1_end = None
        while j < len(sql):
            ch = sql[j]
            if in_str:
                if ch == "'" and j + 1 < len(sql) and sql[j + 1] == "'":
                    j += 2
                    continue
                elif ch == "'":
                    in_str = False
            else:
                if ch == "'":
                    in_str = True
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                elif ch == "," and depth == 1:
                    arg1_end = j
                    break
            j += 1

        if arg1_end is None:
            result.append(sql[best_pos : best_pos + len(best_fn_str)])
            i = best_pos + len(best_fn_str)
            continue

        resource_expr = sql[open_paren + 1 : arg1_end].strip()

        # Extract path string (second argument)
        k = arg1_end + 1
        while k < len(sql) and sql[k] in " \t\n":
            k += 1
        if k >= len(sql) or sql[k] != "'":
            result.append(sql[best_pos : best_pos + len(best_fn_str)])
            i = best_pos + len(best_fn_str)
            continue

        k += 1  # skip opening quote
        path_chars: list[str] = []
        while k < len(sql):
            ch = sql[k]
            if ch == "'" and k + 1 < len(sql) and sql[k + 1] == "'":
                path_chars.append("''")
                k += 2
                continue
            elif ch == "'":
                k += 1
                break
            else:
                path_chars.append(ch)
                k += 1

        path_raw = "".join(path_chars)

        # Consume closing ) of the function call
        while k < len(sql) and sql[k] in " \t\n":
            k += 1
        if k >= len(sql) or sql[k] != ")":
            result.append(sql[best_pos : best_pos + len(best_fn_str)])
            i = best_pos + len(best_fn_str)
            continue

        call_end = k + 1
        path_unescaped = path_raw.replace("''", "'")

        translated = None
        if best_fn_type == "bool" and ".where(" in path_unescaped and ".exists()" in path_unescaped:
            translated = _translate_fhirpath_bool_where(resource_expr, path_raw)
        elif best_fn_type == "text" and path_unescaped.startswith("extension.where(url="):
            translated = _translate_fhirpath_text_extension(resource_expr, path_raw)
        elif best_fn_type == "number" and ".where(" in path_unescaped:
            translated = _translate_fhirpath_number_where(resource_expr, path_raw)

        result.append(translated if translated else sql[best_pos:call_end])
        i = call_end

    return "".join(result)


def postprocess_audit_sql(sql: str) -> str:
    """
    Post-process pre-translated CQL audit SQL for browser execution.
    Runs steps 1 (list_extract removal), 2 (fhirpath replacement),
    4 (MATERIALIZED), and 5 (population cascade gating for pop-only audit).
    Skips step 3 (scalar-subquery boolean wrapper) — audit SQL uses compact_audit()
    macros which produce structs, not plain booleans.
    """
    # Step 1: remove list_extract wrappers
    prev = None
    while prev != sql:
        prev = sql
        sql = re.sub(
            r"list_extract\(\s*fhirpath_text\(([^,]+),\s*'([^']+)'\)\s*,\s*\d+\s*\)",
            r"fhirpath_text(\1, '\2')",
            sql,
        )
    # Step 2: translate complex FHIRPath calls to SQL
    sql = _find_and_replace_fhirpath(sql)

    # Step 4: MATERIALIZED hints are intentionally omitted for WASM demo SQL.
    # The WASM demo uses only 33 test patients; MATERIALIZED forces eager CTE
    # evaluation which hurts single-threaded DuckDB-WASM performance on small
    # datasets.  The SET max_expression_depth TO 10000 in the preamble prevents
    # expression depth errors that MATERIALIZED was also meant to avoid.

    # Step 5 (audit variant): Apply CQL population cascade gating for population-only
    # audit SQL. Full audit SQL (CMS124 tier) handles gating via audit_and/audit_or
    # expressions in each CTE. Population-only audit SQL uses the simpler pattern:
    #   compact_audit(struct_pack(result := CASE WHEN "X".patient_id IS NOT NULL ...))
    # Gate Denominator on Initial Population membership.
    sql = re.sub(
        r"compact_audit\(struct_pack\("
        r"result\s*:=\s*CASE WHEN \"Denominator\"\.patient_id IS NOT NULL THEN TRUE ELSE FALSE END,"
        r"\s*evidence\s*:=\s*\[\]\s*\)\)\s+AS\s+Denominator",
        (
            "compact_audit(struct_pack("
            "result := CASE WHEN \"Denominator\".patient_id IS NOT NULL "
            "AND \"Initial Population\".patient_id IS NOT NULL THEN TRUE ELSE FALSE END,"
            " evidence := [])) AS Denominator"
        ),
        sql,
    )
    # Gate Numerator on Initial Population AND not in Denominator Exclusions.
    sql = re.sub(
        r"compact_audit\(struct_pack\("
        r"result\s*:=\s*CASE WHEN \"Numerator\"\.patient_id IS NOT NULL THEN TRUE ELSE FALSE END,"
        r"\s*evidence\s*:=\s*\[\]\s*\)\)\s+AS\s+Numerator",
        (
            "compact_audit(struct_pack("
            "result := CASE WHEN \"Numerator\".patient_id IS NOT NULL "
            "AND \"Initial Population\".patient_id IS NOT NULL "
            "AND \"Denominator Exclusions\".patient_id IS NULL THEN TRUE ELSE FALSE END,"
            " evidence := [])) AS Numerator"
        ),
        sql,
    )
    return sql


def postprocess_sql(sql: str) -> str:
    """
    Post-process pre-translated CQL SQL for browser execution:
    1. Remove list_extract(fhirpath_text(...), N) wrappers.
    2. Replace complex fhirpath_bool/fhirpath_text expressions with SQL equivalents.
    3. Unwrap scalar-subquery boolean wrappers in the final SELECT.
    4. Add MATERIALIZED to non-valueset CTEs to prevent expression-tree explosion.
    5. Apply CQL population cascade gating in the final SELECT:
       - Denominator is gated on Initial Population
       - Numerator is gated on Initial Population AND NOT Denominator Exclusions
    """
    # Step 1: remove list_extract wrappers
    prev = None
    while prev != sql:
        prev = sql
        sql = re.sub(
            r"list_extract\(\s*fhirpath_text\(([^,]+),\s*'([^']+)'\)\s*,\s*\d+\s*\)",
            r"fhirpath_text(\1, '\2')",
            sql,
        )
    # Step 2: translate complex FHIRPath calls to SQL
    sql = _find_and_replace_fhirpath(sql)

    # Step 3: remove scalar-subquery boolean wrappers that DuckDB re-evaluates per row.
    # The CQL translator may emit these with either inline or multiline formatting:
    #   (SELECT CASE WHEN "CTE".patient_id IS NOT NULL THEN TRUE ELSE FALSE END)
    #   or multiline with extra whitespace/newlines
    # → "CTE".patient_id IS NOT NULL
    sql = re.sub(
        r"\(\s*SELECT\s+CASE\s+WHEN\s+(\"[^\"]+\")\.patient_id\s+IS\s+NOT\s+NULL"
        r"\s+THEN\s+TRUE\s+ELSE\s+FALSE\s+END\s*\)",
        r"\1.patient_id IS NOT NULL",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Step 4: MATERIALIZED hints are intentionally omitted for WASM demo SQL.
    # MATERIALIZED forces eager CTE evaluation which hurts performance on small
    # datasets (33 test patients) in DuckDB-WASM's single-threaded environment.
    # The benchmarking runner applies MATERIALIZED separately for server queries.

    # Step 5: Apply CQL population cascade gating in the final SELECT.
    # The CQL standard gates each population on its parent:
    #   Denominator requires Initial Population
    #   Numerator requires Denominator (and excludes Denominator Exclusions)
    # Without gating, patients outside IP may appear in Numerator (SQL artifact).
    sql = re.sub(
        r'"Denominator"\.patient_id IS NOT NULL AS Denominator',
        '"Denominator".patient_id IS NOT NULL AND "Initial Population".patient_id IS NOT NULL AS Denominator',
        sql,
    )
    # Gate Numerator on IP AND not in Denominator Exclusions (try both singular and plural)
    sql = re.sub(
        r'"Numerator"\.patient_id IS NOT NULL AS Numerator',
        ('"Numerator".patient_id IS NOT NULL'
         ' AND "Initial Population".patient_id IS NOT NULL'
         ' AND "Denominator Exclusions".patient_id IS NULL AS Numerator'),
        sql,
    )
    return sql


# ─── Function call inline expansion ──────────────────────────────────────────

def _extract_call_args(sql: str, open_paren_pos: int) -> tuple[int, list[str]] | None:
    """Parse arguments starting at the '(' at open_paren_pos.
    Returns (end_pos, [arg1, ...]) where end_pos is after closing ')'.
    """
    i = open_paren_pos + 1
    args: list[str] = []
    cur: list[str] = []
    depth = 0
    in_str = False
    q_char = ""
    while i < len(sql):
        c = sql[i]
        if in_str:
            if c == q_char:
                if i + 1 < len(sql) and sql[i + 1] == q_char:
                    cur.append(c)
                    cur.append(c)
                    i += 2
                    continue
                in_str = False
            cur.append(c)
        else:
            if c in ("'", '"'):
                in_str, q_char = True, c
                cur.append(c)
            elif c == "(":
                depth += 1
                cur.append(c)
            elif c == ")":
                if depth == 0:
                    args.append("".join(cur))
                    return (i + 1, args)
                depth -= 1
                cur.append(c)
            elif c == "," and depth == 0:
                args.append("".join(cur))
                cur = []
            else:
                cur.append(c)
        i += 1
    return None


def _expand_function_call(sql: str, fn_name: str, expander) -> str:
    """Replace all calls to fn_name(...) with expander(args_list), innermost-first."""
    pattern = fn_name + "("
    pat_len = len(pattern)
    result: list[str] = []
    i = 0
    in_str = False
    q_char = ""
    while i < len(sql):
        c = sql[i]
        if in_str:
            if c == q_char:
                if i + 1 < len(sql) and sql[i + 1] == q_char:
                    result.append(c)
                    result.append(c)
                    i += 2
                    continue
                in_str = False
            result.append(c)
            i += 1
        elif c in ("'", '"'):
            in_str, q_char = True, c
            result.append(c)
            i += 1
        elif sql[i : i + pat_len] == pattern:
            # Don't match if preceded by an identifier char (e.g. _myfhirpath_text)
            if i > 0 and (sql[i - 1].isalnum() or sql[i - 1] == "_"):
                result.append(c)
                i += 1
                continue
            parsed = _extract_call_args(sql, i + len(fn_name))
            if parsed is None:
                result.append(c)
                i += 1
            else:
                end_pos, args = parsed
                # Recursively expand inner calls within each argument (innermost-first)
                expanded_args = [_expand_function_call(arg, fn_name, expander) for arg in args]
                try:
                    result.append(expander(expanded_args))
                except Exception:
                    result.append(sql[i:end_pos])
                i = end_pos
        else:
            result.append(c)
            i += 1
    return "".join(result)


# FHIR paths that represent JSON objects (not scalars) — use json_extract + CAST
_FHIRPATH_OBJ_PATHS = {
    "period", "effectivePeriod", "performedPeriod", "onset", "onsetPeriod",
    "abatementPeriod", "identifier", "class", "medicationCodeableConcept",
    "codeCodeableConcept", "valueCodeableConcept", "valueQuantity",
    "clinicalStatus", "verificationStatus", "basedOn", "partOf", "recorder",
    "requester", "subject", "encounter", "participant", "performer", "author",
}


def _unquote_sql_str(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('""', '"')
    return s


def _exp_fhirpath_text(args: list[str]) -> str:
    r = args[0].strip()
    # args[1] is a SQL-quoted string like 'status' or 'extension.where(url=''http://...'').value'
    raw_arg = args[1].strip()
    # Extract the inner path text (strip outer quotes, keep '' escaping for translators)
    if len(raw_arg) >= 2 and raw_arg[0] == "'" and raw_arg[-1] == "'":
        path_sql_inner = raw_arg[1:-1]  # e.g. extension.where(url=''http://...'').value
    else:
        path_sql_inner = raw_arg
    path = path_sql_inner.replace("''", "'")  # fully unescaped

    # Delegate complex FHIRPath expressions to existing translators
    if path.startswith("extension.where(url="):
        translated = _translate_fhirpath_text_extension(r, path_sql_inner)
        if translated:
            return translated
        return "NULL"  # unsupported extension pattern

    # Other .where() filter expressions can't be evaluated as JSON paths
    if ".where(" in path:
        return "NULL"

    if path == "effective":
        return (
            "COALESCE(json_extract_string(" + r + "::JSON,'$.effectiveDateTime'),"
            "CAST(json_extract(" + r + "::JSON,'$.effectivePeriod')AS VARCHAR),"
            "json_extract_string(" + r + "::JSON,'$.effectiveInstant'))"
        )
    if path == "performed":
        return (
            "COALESCE(json_extract_string(" + r + "::JSON,'$.performedDateTime'),"
            "CAST(json_extract(" + r + "::JSON,'$.performedPeriod')AS VARCHAR),"
            "json_extract_string(" + r + "::JSON,'$.performed'))"
        )
    if path == "value":
        return (
            "COALESCE(CAST(json_extract(" + r + "::JSON,'$.valueCodeableConcept')AS VARCHAR),"
            "json_extract_string(" + r + "::JSON,'$.valueString'),"
            "CAST(json_extract(" + r + "::JSON,'$.valueQuantity')AS VARCHAR))"
        )
    if path in _FHIRPATH_OBJ_PATHS:
        return "CAST(json_extract(" + r + "::JSON,'$." + path_sql_inner + "')AS VARCHAR)"
    # Simple scalar path — use path_sql_inner (retains '' escaping for SQL string literal)
    return "json_extract_string(" + r + "::JSON,'$." + path_sql_inner + "')"


def _exp_fhirpath_date(args: list[str]) -> str:
    r = args[0].strip()
    raw_arg = args[1].strip()
    if len(raw_arg) >= 2 and raw_arg[0] == "'" and raw_arg[-1] == "'":
        path_sql_inner = raw_arg[1:-1]
    else:
        path_sql_inner = raw_arg
    return "json_extract_string(" + r + "::JSON,'$." + path_sql_inner + "')"


def _exp_fhirpath_bool(args: list[str]) -> str:
    r = args[0].strip()
    raw_arg = args[1].strip()
    if len(raw_arg) >= 2 and raw_arg[0] == "'" and raw_arg[-1] == "'":
        path_sql_inner = raw_arg[1:-1]
    else:
        path_sql_inner = raw_arg
    return "TRY_CAST(json_extract_string(" + r + "::JSON,'$." + path_sql_inner + "')AS BOOLEAN)"


def _exp_fhirpath_number(args: list[str]) -> str:
    r = args[0].strip()
    raw_arg = args[1].strip()
    if len(raw_arg) >= 2 and raw_arg[0] == "'" and raw_arg[-1] == "'":
        path_sql_inner = raw_arg[1:-1]
    else:
        path_sql_inner = raw_arg
    return "TRY_CAST(json_extract_string(" + r + "::JSON,'$." + path_sql_inner + "')AS DOUBLE)"


def _exp_fhirpath(args: list[str]) -> str:
    r = args[0].strip()
    raw_arg = args[1].strip()
    if len(raw_arg) >= 2 and raw_arg[0] == "'" and raw_arg[-1] == "'":
        path_sql_inner = raw_arg[1:-1]
    else:
        path_sql_inner = raw_arg
    path = path_sql_inner.replace("''", "'")
    # FHIRPath filter expressions are not valid JSON paths
    if ".where(" in path or ".exists(" in path or ".ofType(" in path:
        return "NULL"
    return "CAST(json_extract(" + r + "::JSON,'$." + path_sql_inner + "')AS VARCHAR)"


def _exp_intervalFromBounds(args: list[str]) -> str:
    s = args[0].strip()
    e = args[1].strip()
    lc = args[2].strip()
    hc = args[3].strip()
    # Bind s/e/lc/hc once, then compute — avoids repeating complex expressions
    return (
        "(SELECT ('{'||'\"low\":'||COALESCE('\"'||_s||'\"','null')"
        "||',\"high\":'||COALESCE('\"'||_e||'\"','null')"
        "||',\"lowClosed\":'||CASE WHEN _lc THEN 'true' ELSE 'false' END"
        "||',\"highClosed\":'||CASE WHEN _hc THEN 'true' ELSE 'false' END||'}')"
        " FROM (SELECT (" + s + ") AS _s,(" + e + ") AS _e,"
        "(" + lc + ") AS _lc,(" + hc + ") AS _hc) _ib)"
    )


def _exp_intervalStart(args: list[str]) -> str:
    iv = args[0].strip()
    return (
        "(SELECT CASE WHEN _iv IS NULL THEN NULL"
        " WHEN starts_with(ltrim(_iv),'{') THEN"
        " COALESCE(json_extract_string(_iv,'$.low'),json_extract_string(_iv,'$.start'))"
        " ELSE _iv END FROM (SELECT (" + iv + ") AS _iv) _is)"
    )


def _exp_intervalEnd(args: list[str]) -> str:
    iv = args[0].strip()
    return (
        "(SELECT CASE WHEN _iv IS NULL THEN NULL"
        " WHEN starts_with(ltrim(_iv),'{') THEN"
        " COALESCE(json_extract_string(_iv,'$.high'),json_extract_string(_iv,'$.end'))"
        " ELSE _iv END FROM (SELECT (" + iv + ") AS _iv) _ie)"
    )


def _exp_intervalOverlaps(args: list[str]) -> str:
    iv1 = args[0].strip()
    iv2 = args[1].strip()
    # NULL high/low in a JSON interval means unbounded (open-ended).
    # iv1 overlaps iv2 iff:
    #   (iv1.high IS NULL  OR iv1.high >= iv2.low)   -- iv1 upper bound vs iv2 lower bound
    #   AND
    #   (iv2.high IS NULL  OR iv1.low  <= iv2.high)   -- iv1 lower bound vs iv2 upper bound
    return (
        "(SELECT CASE WHEN _iv1 IS NULL OR _iv2 IS NULL THEN FALSE ELSE"
        # Condition 1: iv1 upper bound >= iv2 lower bound
        " (CASE WHEN starts_with(ltrim(_iv1),'{')"
        "  THEN json_extract_string(_iv1,'$.high') IS NULL"
        "    OR TRY_CAST(json_extract_string(_iv1,'$.high') AS TIMESTAMP)"
        "       >=TRY_CAST(COALESCE(json_extract_string(_iv2,'$.low'),json_extract_string(_iv2,'$.start'),_iv2) AS TIMESTAMP)"
        "  ELSE TRY_CAST(_iv1 AS TIMESTAMP)"
        "       >=TRY_CAST(COALESCE(json_extract_string(_iv2,'$.low'),json_extract_string(_iv2,'$.start'),_iv2) AS TIMESTAMP)"
        " END)"
        # Condition 2: iv1 lower bound <= iv2 upper bound
        " AND (CASE WHEN starts_with(ltrim(_iv2),'{')"
        "  THEN json_extract_string(_iv2,'$.high') IS NULL"
        "    OR TRY_CAST(COALESCE(json_extract_string(_iv1,'$.low'),json_extract_string(_iv1,'$.start'),_iv1) AS TIMESTAMP)"
        "       <=TRY_CAST(json_extract_string(_iv2,'$.high') AS TIMESTAMP)"
        "  ELSE TRY_CAST(COALESCE(json_extract_string(_iv1,'$.low'),json_extract_string(_iv1,'$.start'),_iv1) AS TIMESTAMP)"
        "       <=TRY_CAST(_iv2 AS TIMESTAMP)"
        " END)"
        " END FROM (SELECT (" + iv1 + ") AS _iv1,(" + iv2 + ") AS _iv2) _io)"
    )


def _make_date_arith(sign: str):
    def expander(args: list[str]) -> str:
        d = args[0].strip()
        q = args[1].strip()
        return (
            "(SELECT CASE WHEN _d IS NULL OR _q IS NULL THEN NULL ELSE"
            " CAST(CASE json_extract_string(_q,'$.unit')"
            " WHEN 'year' THEN TRY_CAST(_d AS DATE)" + sign + "to_years(CAST(ROUND(TRY_CAST(json_extract_string(_q,'$.value')AS DOUBLE))AS INTEGER))"
            " WHEN 'a' THEN TRY_CAST(_d AS DATE)" + sign + "to_years(CAST(ROUND(TRY_CAST(json_extract_string(_q,'$.value')AS DOUBLE))AS INTEGER))"
            " WHEN 'month' THEN TRY_CAST(_d AS DATE)" + sign + "to_months(CAST(ROUND(TRY_CAST(json_extract_string(_q,'$.value')AS DOUBLE))AS INTEGER))"
            " WHEN 'mo' THEN TRY_CAST(_d AS DATE)" + sign + "to_months(CAST(ROUND(TRY_CAST(json_extract_string(_q,'$.value')AS DOUBLE))AS INTEGER))"
            " WHEN 'day' THEN TRY_CAST(_d AS DATE)" + sign + "to_days(CAST(ROUND(TRY_CAST(json_extract_string(_q,'$.value')AS DOUBLE))AS INTEGER))"
            " WHEN 'd' THEN TRY_CAST(_d AS DATE)" + sign + "to_days(CAST(ROUND(TRY_CAST(json_extract_string(_q,'$.value')AS DOUBLE))AS INTEGER))"
            " ELSE TRY_CAST(_d AS DATE) END AS VARCHAR) END"
            " FROM (SELECT (" + d + ") AS _d,(" + q + ") AS _q) _da)"
        )
    return expander


def _exp_parse_quantity(args: list[str]) -> str:
    v = args[0].strip()
    # Converts a FHIR Quantity JSON string to a struct with value/code/system/unit fields.
    # Uses a subquery to bind v once (avoids repeated evaluation of complex expressions).
    return (
        "(SELECT CASE WHEN _pq IS NULL THEN NULL ELSE"
        " struct_pack("
        "\"value\" := TRY_CAST(json_extract_string(_pq::JSON,'$.value') AS DOUBLE),"
        "code := COALESCE(json_extract_string(_pq::JSON,'$.code'),json_extract_string(_pq::JSON,'$.unit')),"
        "system := COALESCE(json_extract_string(_pq::JSON,'$.system'),'http://unitsofmeasure.org'),"
        "unit := json_extract_string(_pq::JSON,'$.unit')) END"
        " FROM (SELECT (" + v + ") AS _pq) _pqt)"
    )


def _inline_all_function_calls(sql: str) -> str:
    """Pre-expand all SQL macro calls so DuckDB needs no macros at query time.
    Uses recursive (innermost-first) expansion within each function type,
    then iterates across function types until stable for cross-function nesting.
    """
    for _ in range(10):  # max iterations for cross-function nesting
        prev = sql
        # Pass 1: leaf-level FHIRPath accessors (recursive per function)
        sql = _expand_function_call(sql, "fhirpath_text", _exp_fhirpath_text)
        sql = _expand_function_call(sql, "fhirpath_date", _exp_fhirpath_date)
        sql = _expand_function_call(sql, "fhirpath_bool", _exp_fhirpath_bool)
        sql = _expand_function_call(sql, "fhirpath_number", _exp_fhirpath_number)
        sql = _expand_function_call(sql, "fhirpath", _exp_fhirpath)
        # Pass 2: interval construction
        sql = _expand_function_call(sql, "intervalFromBounds", _exp_intervalFromBounds)
        # Pass 3: interval accessors
        sql = _expand_function_call(sql, "intervalStart", _exp_intervalStart)
        sql = _expand_function_call(sql, "intervalEnd", _exp_intervalEnd)
        # Pass 4: higher-order interval ops + date arithmetic + quantity parsing
        sql = _expand_function_call(sql, "intervalOverlaps", _exp_intervalOverlaps)
        sql = _expand_function_call(sql, "dateSubtractQuantity", _make_date_arith("-"))
        sql = _expand_function_call(sql, "dateAddQuantity", _make_date_arith("+"))
        sql = _expand_function_call(sql, "parse_quantity", _exp_parse_quantity)
        if sql == prev:
            break
    return sql


# ─── Valueset inline expansion ────────────────────────────────────────────────
# These paths refer to array-of-CodeableConcept FHIR fields (e.g. Encounter.type).
_ARRAY_CC_PATHS = {"type", "category"}
# These paths are FHIR choice types (e.g. Observation.value → valueCodeableConcept).
_CHOICE_TYPE_PATHS = {"value"}


def _split_simple_args(text: str) -> list[str]:
    """Split top-level comma-separated args, respecting strings and parens."""
    args: list[str] = []
    cur: list[str] = []
    depth = 0
    in_str = False
    q_char = ""
    for c in text:
        if in_str:
            if c == q_char:
                in_str = False
            cur.append(c)
        else:
            if c in ("'", '"'):
                in_str, q_char = True, c
                cur.append(c)
            elif c == "(":
                depth += 1
                cur.append(c)
            elif c == ")":
                depth -= 1
                cur.append(c)
            elif c == "," and depth == 0:
                args.append("".join(cur))
                cur = []
            else:
                cur.append(c)
    if cur:
        args.append("".join(cur))
    return args


def _build_cte_in_valueset(resource_expr: str, path: str, cte_name: str) -> str:
    """Build EXISTS … JOIN against a pre-built valueset CTE."""
    esc_r = resource_expr.replace("'", "''")
    if path in _ARRAY_CC_PATHS:
        unnest_sql = (
            f"unnest(flatten(COALESCE(list_transform("
            f"COALESCE(from_json(json_extract({resource_expr}::JSON, '$.{path}'), '[\"JSON\"]'), CAST([] AS JSON[])),"
            f" _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '[\"JSON\"]'), CAST([] AS JSON[]))"
            f"), CAST([] AS JSON[][])))) AS _c"
        )
    elif path in _CHOICE_TYPE_PATHS:
        unnest_sql = (
            f"unnest(COALESCE("
            f"from_json(json_extract({resource_expr}::JSON, '$.{path}CodeableConcept.coding'), '[\"JSON\"]'),"
            f"from_json(json_extract({resource_expr}::JSON, '$.{path}.coding'), '[\"JSON\"]'),"
            f"CAST([] AS JSON[]))) AS _c"
        )
    else:
        unnest_sql = (
            f"unnest(COALESCE("
            f"from_json(json_extract({resource_expr}::JSON, '$.{path}.coding'), '[\"JSON\"]'),"
            f"CAST([] AS JSON[]))) AS _c"
        )
    return (
        f"EXISTS (SELECT 1 FROM (SELECT {unnest_sql}) _inv"
        f" INNER JOIN {cte_name} ON {cte_name}._vs_code = json_extract_string(_c, '$.code')"
        f" AND ({cte_name}._vs_system = '' OR {cte_name}._vs_system = json_extract_string(_c, '$.system')))"
    )


def _expand_in_valueset_to_ctes(sql: str, vs_codes: dict[str, list[tuple[str, str]]]) -> str:
    """
    Replace in_valueset(resource_expr, 'path', 'vs_url') calls with hash-join-friendly
    CTE references, and inject corresponding valueset CTEs at the top of the WITH clause.
    """
    pattern = "in_valueset("

    # Find all unique vs_urls referenced in the SQL
    used_vs_urls = sorted(set(
        m.group(1)
        for m in re.finditer(r"in_valueset\([^,]+,\s*'[^']+',\s*'([^']+)'", sql)
    ))
    if not used_vs_urls:
        return sql

    vs_cte_name = {url: f"_vs_{i}" for i, url in enumerate(used_vs_urls)}

    # Build CTE SQL blocks
    vs_cte_blocks: list[str] = []
    for url in used_vs_urls:
        name = vs_cte_name[url]
        codes = vs_codes.get(url, [])
        if not codes:
            vs_cte_blocks.append(f"{name}(_vs_system, _vs_code) AS (SELECT '' AS _vs_system, '' AS _vs_code WHERE FALSE)")
            continue
        pairs = ", ".join(
            f"('{s.replace(chr(39), chr(39)*2)}','{c.replace(chr(39), chr(39)*2)}')"
            for s, c in codes
        )
        vs_cte_blocks.append(f"{name}(_vs_system, _vs_code) AS (VALUES {pairs})")

    # Expand each in_valueset call
    result: list[str] = []
    i = 0
    while True:
        pos = sql.find(pattern, i)
        if pos == -1:
            result.append(sql[i:])
            break
        result.append(sql[i:pos])

        # Walk to closing paren
        j = pos + len(pattern)
        depth = 1
        in_str = False
        q_char = ""
        while j < len(sql) and depth > 0:
            c = sql[j]
            if in_str:
                if c == q_char:
                    in_str = False
            else:
                if c in ("'", '"'):
                    in_str, q_char = True, c
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
            j += 1
        call_end = j
        args_text = sql[pos + len(pattern):j - 1]

        args = _split_simple_args(args_text)
        if len(args) != 3:
            result.append(sql[pos:call_end])
            i = call_end
            continue

        resource_expr = args[0].strip()
        path_lit = args[1].strip().strip("'\"")
        vs_url_lit = args[2].strip().strip("'\"")

        cte_name = vs_cte_name.get(vs_url_lit)
        if not cte_name:
            result.append(sql[pos:call_end])
            i = call_end
            continue

        result.append(_build_cte_in_valueset(resource_expr, path_lit, cte_name))
        i = call_end

    expanded = "".join(result)

    # Inject valueset CTEs immediately after the first WITH keyword
    with_match = re.match(r"^(\s*--[^\n]*\n)*\s*WITH\s+", expanded, re.IGNORECASE)
    if with_match and vs_cte_blocks:
        insert_pos = with_match.end()
        ctes_prefix = ",\n".join(vs_cte_blocks) + ",\n"
        expanded = expanded[:insert_pos] + ctes_prefix + expanded[insert_pos:]

    return expanded



# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Prepare CMS demo data for wasm-demo")
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Pre-inline all UDF calls to plain JSON SQL (fallback for environments "
             "without C++ WASM extensions). Default: keep fhirpath/interval UDF calls.",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Generate audit SQL files ({measure_id}_audit.sql) with compact_audit() "
             "struct output for evidence-mode rendering. Uses pre-translated audit SQL "
             "from benchmarking/output/sql/{MEASURE_ID}_audit.sql.",
    )
    args = parser.parse_args()
    use_inline = args.inline
    gen_audit = args.audit

    for measure_id, cfg in MEASURES.items():
        print(f"\n{'='*60}")
        print(f"Processing {measure_id}: {cfg['title']}")
        print(f"{'='*60}")

        # Load pre-translated SQL
        sql_path = SQL_OUTPUT_DIR / cfg["sql_file"]
        if not sql_path.exists():
            print(f"  ERROR: SQL file not found: {sql_path}")
            print(f"  Run: cd benchmarking && USE_CPP_EXTENSIONS=0 python3 -m benchmarking.runner --measure {measure_id} --suite 2025")
            sys.exit(1)

        with open(sql_path) as f:
            raw_sql = f.read()

        sql = strip_patient_id_filter(raw_sql)
        sql = postprocess_sql(sql)

        if use_inline:
            # Inline-expand all SQL macro calls → plain DuckDB SQL (no macros needed in browser)
            print("  Inlining function calls (--inline mode)...")
            sql = _inline_all_function_calls(sql)
        else:
            print("  Keeping C++ UDF calls (use --inline to pre-expand to plain JSON SQL)")

        # Extract valueset codes
        print("  Extracting valueset codes...")
        vs_codes = extract_valuesets_for_sql(sql)

        # Inline-expand in_valueset calls → valueset CTEs (eliminates correlated subqueries)
        print("  Inlining valueset CTEs into SQL...")
        sql = _expand_in_valueset_to_ctes(sql, vs_codes)

        # Verify no in_valueset calls remain
        remaining = len(re.findall(r"\bin_valueset\(", sql))
        if remaining:
            print(f"  WARNING: {remaining} in_valueset calls remain (no codes found for their valuesets)")

        # Save processed SQL
        sql_out = OUT_DIR / f"{measure_id.lower()}.sql"
        with open(sql_out, "w") as f:
            f.write(sql)
        print(f"  SQL written to {sql_out} ({len(sql)} chars)")

        # Flatten valueset codes to list of rows (still useful for debugging/reference)
        vs_rows = []
        for vs_url, codes in vs_codes.items():
            for system, code in codes:
                vs_rows.append({"valueset_url": vs_url, "system": system, "code": code})

        vs_out = OUT_DIR / f"{measure_id.lower()}_valuesets.json"
        with open(vs_out, "w") as f:
            json.dump(vs_rows, f, separators=(",", ":"))
        print(f"  Valueset codes written to {vs_out} ({len(vs_rows)} codes, {vs_out.stat().st_size // 1024}KB)")

        # Extract resources
        print("  Extracting FHIR resources...")
        resources, expected_by_patient = extract_resources_for_measure(cfg["test_dir_name"])

        # Write resources as NDJSON
        res_out = OUT_DIR / f"{measure_id.lower()}_resources.ndjson"
        with open(res_out, "w") as f:
            for r in resources:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        print(f"  Resources written to {res_out} ({res_out.stat().st_size // 1024}KB)")

        # Write expected results
        exp_out = OUT_DIR / f"{measure_id.lower()}_expected.json"
        with open(exp_out, "w") as f:
            json.dump(expected_by_patient, f, separators=(",", ":"))
        print(f"  Expected results written to {exp_out} ({len(expected_by_patient)} patients)")

    # ── Audit SQL generation ──────────────────────────────────────────────────
    if gen_audit:
        print("\n" + "="*60)
        print("Generating audit SQL files (--audit mode)...")
        print("="*60)

        # Import audit macro SQL strings from duckdb_cql_py
        from duckdb_cql_py.macros.audit import AUDIT_MACROS_SQL
        macros_preamble = "-- Raise expression depth for complex nested audit expressions\n"
        macros_preamble += "SET max_expression_depth TO 10000;\n\n"
        macros_preamble += "-- Audit macros (SQL-based, no C++ extension required)\n"
        macros_preamble += ";\n".join(AUDIT_MACROS_SQL) + ";\n\n"

        for measure_id, cfg in MEASURES.items():
            print(f"\n--- {measure_id} ---")
            # Prefer _audit_full.sql (full evidence SQL preserved even when server
            # execution fails due to OOM) over _audit.sql (population-only fallback),
            # unless the measure config explicitly disables it via use_full_audit=False
            # (e.g. when the full audit SQL is too complex for DuckDB-WASM).
            use_full = cfg.get("use_full_audit", True)
            audit_full_path = SQL_OUTPUT_DIR / f"{measure_id}_audit_full.sql"
            audit_sql_path = SQL_OUTPUT_DIR / f"{measure_id}_audit.sql"
            if use_full and audit_full_path.exists():
                chosen = audit_full_path
                print(f"  Using full audit SQL: {chosen.name}")
            elif audit_sql_path.exists():
                chosen = audit_sql_path
                print(f"  Using audit SQL: {chosen.name}")
            else:
                print(f"  SKIP: No audit SQL found for {measure_id}")
                continue

            with open(chosen) as f:
                raw_sql = f.read()

            sql = strip_patient_id_filter(raw_sql)
            sql = postprocess_audit_sql(sql)

            # Expand in_valueset calls → inline CTEs
            vs_codes = extract_valuesets_for_sql(sql)
            sql = _expand_in_valueset_to_ctes(sql, vs_codes)
            remaining = len(re.findall(r"\bin_valueset\(", sql))
            if remaining:
                print(f"  WARNING: {remaining} in_valueset calls remain after expansion")

            # Prepend audit macro definitions so the SQL file is self-contained
            sql = macros_preamble + sql

            audit_out = OUT_DIR / f"{measure_id.lower()}_audit.sql"
            with open(audit_out, "w") as f:
                f.write(sql)
            print(f"  Audit SQL written to {audit_out} ({len(sql):,} chars)")

    # Write index manifest
    manifest = {
        "measures": {
            mid: {
                "title": cfg["title"],
                "populations": cfg["populations"],
                "files": {
                    "sql": f"{mid.lower()}.sql",
                    "auditSql": f"{mid.lower()}_audit.sql",
                    "resources": f"{mid.lower()}_resources.ndjson",
                    "valuesets": f"{mid.lower()}_valuesets.json",
                    "expected": f"{mid.lower()}_expected.json",
                },
            }
            for mid, cfg in MEASURES.items()
        }
    }
    manifest_out = OUT_DIR / "manifest.json"
    with open(manifest_out, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written to {manifest_out}")
    print("\nData preparation complete!")


if __name__ == "__main__":
    main()
