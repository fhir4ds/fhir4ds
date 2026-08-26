# Architectural Audit Inventory
**Date:** 2026-03-02
**Status:** Audit Complete
**Auditor:** GLM-5 (Team Orchestrator)
**Reference:** PLAN-ARCHITECTURAL-REMEDIATION.md

---

## Summary of Findings

| Category | Anti-Pattern | Instances |
|----------|--------------|-----------|
| A | `.to_sql()` for Inspection | 12 |
| A | Regex for SQL Pattern Detection | 11 |
| A | String-Based Column Detection | 45+ |
| A | String-Based Type Detection (`.startswith`/`.endswith`) | 30+ |
| B | Hardcoded Choice Type Maps | 3 |
| B | Hardcoded Column Definitions | 2 |
| B | Hardcoded Valid Column Whitelists | 2 |
| B | Hardcoded Property Mappings | 2 |
| B | Hardcoded Profile Patterns | 2 |
| B | Hardcoded Terminology Properties | 1 |
| B | Hardcoded Library Constants | 3 |
| B | Hardcoded Status Filters | 1 |
| B | Hardcoded Function Templates | 1 |
| C | Heuristic Type Inference | 2 |
| **TOTAL** | | **110+** |

---

## Category A1: `.to_sql()` for Inspection/Decision-Making

*Violates Principle 1: "The translator must never inspect or manipulate SQL text mid-pipeline. All decisions must be made using AST metadata."*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `fluent_functions.py` | 1641 | `resource_sql = resource_expr.to_sql()` | Calls `.to_sql()` during template substitution (Phase 1) to get resource SQL string |
| `fluent_functions.py` | 1682 | `param_map[param_name] = arg.to_sql()` | Converts args to SQL strings for template parameter substitution |
| `fluent_functions.py` | 2133 | `return SQLFunctionCall(...).to_sql()` | Returns rendered SQL string instead of AST node |
| `fluent_functions.py` | 2148 | `resource_sql = self._resource_expr.to_sql()` | DeferredTemplateSubstitution.to_sql() calls to_sql on resource |
| `fluent_functions.py` | 2174 | `param_map[param_name] = arg.to_sql()` | Parameter map built with SQL strings |
| `context.py` | 617 | `self.definitions[name] = ast_expr.to_sql()` | Stores rendered SQL instead of AST in definitions dict |
| `expressions.py` | 1109 | `resource_col = SQLQualifiedIdentifier(parts=[source_sql.to_sql(), "resource"])` | Uses to_sql() to build qualified identifier parts |
| `patterns/aggregation.py` | 302 | `source_sql_str = source_sql.to_sql()` | Calls to_sql() for inspection of source expression |
| `patterns/joins.py` | 569 | `return sql_expr.to_sql()` | Returns rendered SQL instead of AST |

---

## Category A2: Regex for SQL Pattern Detection

*Violates Principle 1: Regex-based SQL inspection is brittle and bypasses AST structure.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `fluent_functions.py` | 1461 | `if re.search(unsafe_quote_pattern, template):` | Regex check for unsafe quoting in templates |
| `fluent_functions.py` | 1576-1582 | `pattern = rf"{func_name}\(r,\s*'{re.escape(fhirpath)}'\)"` ... `template = re.sub(pattern, replacement, template)` | Regex replacement of fhirpath calls with column refs |
| `fluent_functions.py` | 1806 | `match = re.match(r'list_filter\(\{resource\},\s*(\w+)\s*->\s*(.+)\)$', template.strip())` | Regex extraction of lambda predicate from list_filter template |
| `fluent_functions.py` | 1811 | `scalar_predicate = re.sub(r'\b' + re.escape(lambda_var) + r'\b', resource_sql, predicate)` | Regex substitution of lambda variable in predicate |
| `fluent_functions.py` | 1877 | `re.search(r'\bCASE\b', resource_upper) is not None` | Regex detection of CASE expressions for scalar/list dispatch |
| `fluent_functions.py` | 1951 | `if re.match(simple_identifier_pattern, resource_sql.strip()):` | Regex check for simple SQL identifier pattern |
| `fluent_functions.py` | 1966 | `has_correlated_ref = re.search(correlated_pattern, resource_sql) is not None` | Regex detection of correlated CTE references |
| `expressions.py` | 516 | `if re.search(r'THEN\s*\(\s*SELECT', sql_expr_val, re.IGNORECASE)` | Regex detection of CASE+UNION pattern in SQL string |
| `property_scanner.py` | 122 | `match = re.search(r"\bcode\s*=\s*['\"](\d{4,5}-\d+)['\"]", where_content)` | Regex extraction of LOINC codes from FHIRPath strings |
| `ast_utils.py` | 27 | `return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()` | Regex-based camelCase to snake_case conversion |
| `expressions.py` | 5302, 5421 | `match = re.match(...)` | Regex pattern matching for temporal operators |

---

## Category A3: String-Based Column/Pattern Detection

*Violates Principle 1: String inspection bypasses AST metadata, making code brittle and error-prone.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `expressions.py` | 511 | `if 'CASE WHEN' in sql_expr_val.upper() and 'UNION ALL' in sql_expr_val.upper():` | String check for CASE+UNION pattern |
| `expressions.py` | 522 | `is_list_expr = any(op in sql_expr_val for op in ['list_filter', 'jsonConcat', 'list_apply'])` | String check for list expressions |
| `fluent_functions.py` | 1448 | `if '--' in resource_sql:` | String check for SQL comments |
| `fluent_functions.py` | 1452 | `if "'''" in template or '"""' in template:` | String check for triple quotes |
| `fluent_functions.py` | 1456 | `if ';' in resource_sql:` | String check for semicolons |
| `fluent_functions.py` | 1660-1661 | `if (f"{fhir_func}{param_placeholder}" in template or ...)` | String check for placeholder patterns |
| `fluent_functions.py` | 1705 | `if "FROM {resource}" in result:` | String check for FROM clause |
| `fluent_functions.py` | 1739 | `elif "list_filter({resource}" in template:` | String check for list_filter template |
| `fluent_functions.py` | 1751-1752 | `"fhirpath_text({resource}" in template and ("=" in template or " IN " in template)` | String checks for fhirpath template patterns |
| `fluent_functions.py` | 1878-1882 | `'COALESCE(' in resource_upper or 'NULLIF(' in resource_upper or ...` | Multiple string checks for scalar expression detection |
| `fluent_functions.py` | 2153 | `if "fhirpath_text({resource}" in self._template or ...` | String check for fhirpath function in template |
| `fluent_functions.py` | 2194-2208 | Multiple `in self._template` checks | String-based template pattern detection |
| `cte_builder.py` | 223 | `if "blood-pressure" in url.lower() or "bp" in url.lower():` | String check for BP profile URL |
| `cte_builder.py` | 499 | `if "profiles" in col_def:` | String check for profile-specific columns |
| `cte_builder.py` | 558-562 | `if "date" in fhirpath_func.lower():` ... `elif "bool" in fhirpath_func.lower():` | Substring matching for UDF type inference |
| `property_scanner.py` | 66 | `return "component.where(" in property_path` | String check for component.where pattern |
| `types.py` | 314 | `if isinstance(first_arg, SQLRaw) and " UNION ALL " in first_arg.raw_sql.upper():` | String check for UNION ALL in raw SQL |
| `translator.py` | 1593, 1599, 2843, 2851, 2865 | `if ':' in cte_name:` | String check for qualified CTE names |
| `translator.py` | 2180 | `if not table_name.lower().endswith(' r') and ' as r' not in table_name.lower():` | String check for table alias patterns |
| `translator.py` | 414 | `elif "Initial Population" in definitions:` | String check for definition name |
| `expressions.py` | 953, 990 | `if "date" in path.lower() or "time" in path.lower():` | Substring matching for date property detection |
| `expressions.py` | 1281 | `existing_func = source_sql.name.split('_')[1] if '_' in source_sql.name else 'text'` | String split for function type extraction |
| `expressions.py` | 1324 | `if "." in source_str and (source_str.endswith(".resource") or ...)` | String check for resource column reference |
| `expressions.py` | 1859, 1863 | `if ":" in name:` | String check for qualified names |
| `expressions.py` | 2626, 2726, 2836, 2838 | `if " or " in inner_op:` | String check for OR operator |
| `expressions.py` | 3630 | `return 'component' in path_lower` | Substring check for component path |
| `expressions.py` | 3737 | `if code_def and "code" in code_def:` | String check for code definition |
| `expressions.py` | 3810-3814 | `if 'quantity' in path or 'value' in path:` ... `elif 'date' in path or 'time' in path:` | Substring matching for type inference |
| `types.py` | 899 | `if ',' in fhirpath:` | String check for comma in FHIRPath |
| `patterns/aggregation.py` | 305 | `if "jsonConcat" in source_sql_str.lower() or "list_filter" in source_sql_str.lower():` | String check for list expressions |

---

## Category B1: Hardcoded Choice Type Maps

*Violates Principle 2: "Profiles are inferred from CQL usage patterns, not from a hardcoded registry."*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `types.py` | 1053-1155 | `CHOICE_TYPE_COLUMNS = { "effective_date": {...}, "onset_date": {...}, ... }` | 15 hardcoded precomputed column definitions with embedded FHIRPath, LOINC codes, and profile URLs |
| `types.py` | 1161-1173 | `DEFAULT_SORT_COLUMNS = { "Condition": [...], "Observation": [...], ... }` | 11 hardcoded sort column definitions as raw SQL strings |
| `cte_builder.py` | 570-572 | `choice_type_patterns = {"value", "onset", "effective", "performed"}` | Hardcoded choice type prefix patterns for column detection |

---

## Category B2: Hardcoded Valid Column Whitelists

*Violates Principle 2: Property validation should use schema, not static whitelists.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cte_builder.py` | 43-92 | `RESOURCE_TYPE_VALID_COLUMNS = { "Condition": {...}, "Observation": {...}, ... }` | 14 resource types with hardcoded valid column whitelists |
| `cte_builder.py` | 99-111 | `PROPERTY_CHAIN_COLUMNS = { "Encounter": {...}, "Observation": {...} }` | 4 hardcoded deep property chain mappings with raw SQL |

---

## Category B3: Hardcoded Property-to-Column Mappings

*Violates Principle 2: Column naming should be schema-aware, not heuristic-based.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cte_builder.py` | 114-174 | `def property_to_column_name(...)` with `column_map = {...}` | 18 hardcoded FHIRPath -> column name mappings |
| `cte_builder.py` | 177-214 | `def infer_fhirpath_function(...)` | Heuristic-based UDF inference using substring matching on property names |

---

## Category B4: Hardcoded Profile Patterns

*Violates Principle 2: Profile metadata should come from StructureDefinitions.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cte_builder.py` | 583-597 | `PROFILES_REQUIRING_SUFFIX = { "http://hl7.org/fhir/us/core/...": "...", ... }` | 9 hardcoded US Core profile URLs requiring CTE suffix |
| `patterns/retrieve.py` | 45-60 | `_TERMINOLOGY_PROPERTY_DEFAULTS = { "Condition": "code", ... }` | 12 hardcoded default terminology property mappings |
| `patterns/retrieve.py` | 63-73 | `_CODESYSTEM_PREFIXES = { "LOINC": "http://loinc.org", ... }` | 9 hardcoded code system URL prefixes |

---

## Category B5: Hardcoded Library Constants

*Violates Principle 2: Library constants should be extracted from parsed CQL ASTs.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `expressions.py` | 88-122 | `_LIBRARY_CODE_CONSTANTS = { "allergy-confirmed": "confirmed", ... }` | ~40 hardcoded QICoreCommon code constants bypassing library parsing |
| `expressions.py` | 229-232 | `COMPONENT_CODE_TO_COLUMN = { "8480-6": "systolic_value", "8462-4": "diastolic_value" }` | 2 hardcoded LOINC code -> column mappings |
| `property_scanner.py` | 41-44 | `BP_LOINC_CODES = { "8480-6": "systolic", "8462-4": "diastolic" }` | 2 hardcoded BP LOINC codes (duplicated from expressions.py) |

---

## Category B6: Hardcoded Status Filters

*Violates Principle 2: Status filter logic should be extracted from parsed CQL library function bodies.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `fluent_functions.py` | 62-196 | `STATUS_FILTERS = { "isObservationBP": {...}, "isProcedurePerformed": {...}, ... }` | 25+ hardcoded status filter rules mapping function names to status field + allowed values |

---

## Category B7: Hardcoded Function Templates

*Violates Principle 2: Function bodies should be inlined from parsed CQL libraries.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `fluent_functions.py` | 417-802 | `def _initialize_common_functions(self)` | 30+ body_sql string templates with embedded FHIRPath registered for common fluent functions |

---

## Category B8: Hardcoded FHIRPath Builders

*Violates Principle 2: Prevalence/date logic should come from parsed library function bodies.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `fluent_functions.py` | 1200-1299 | `def _build_prevalence_interval_ast(...)` | Hardcoded onset/abatement/recorded FHIRPath patterns for prevalenceInterval |
| `fluent_functions.py` | 1382-1420 | `def _build_date_coalesce_expr(...)` | Hardcoded effective date COALESCE order for date extraction |

---

## Category C1: Heuristic Type Inference

*Violates Principle 3: Type inference should use FHIR schema, not substring matching.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cte_builder.py` | 199-214 | `if any(x in property_lower for x in ['date', 'time', 'period']):` ... `elif any(x in property_lower for x in ['active', 'deceased']):` | Heuristic UDF selection based on property name substrings |
| `expressions.py` | 3810-3814 | `if 'quantity' in path or 'value' in path:` ... `elif 'date' in path or 'time' in path:` | Heuristic type inference for property access |

---

## Files by Violation Count

| File | Total Violations | Categories |
|------|------------------|------------|
| `fluent_functions.py` | **28** | A1, A2, A3, B6, B7, B8 |
| `cte_builder.py` | **12** | A3, B1, B2, B3, B4, C1 |
| `expressions.py` | **11** | A1, A2, A3, B5, C1 |
| `types.py` | **6** | A3, B1 |
| `patterns/retrieve.py` | **3** | B4 |
| `property_scanner.py` | **3** | A2, A3, B5 |
| `patterns/aggregation.py` | **2** | A1, A3 |
| `context.py` | **1** | A1 |
| `patterns/joins.py` | **1** | A1 |
| `ast_utils.py` | **1** | A2 |
| `translator.py` | **5** | A3 |

---

## Remediation Priority

Based on severity and impact:

### P0 - Critical (Blocks Other Work)
1. **A1: `.to_sql()` for Inspection** - Must be fixed before AST utilities can work properly
2. **A2: Regex for SQL Pattern Detection** - Core architectural violation

### P1 - High (Affects Correctness)
3. **B6: Hardcoded Status Filters** - Prevents supporting new library versions
4. **B5: Hardcoded Library Constants** - Same as above
5. **B1: Hardcoded Choice Type Maps** - Prevents supporting new FHIR versions

### P2 - Medium (Affects Maintainability)
6. **B2: Hardcoded Valid Column Whitelists** - Manual updates required for new resources
7. **B3: Hardcoded Property Mappings** - Heuristics may fail on edge cases
8. **B7: Hardcoded Function Templates** - Should inline from parsed CQL

### P3 - Low (Technical Debt)
9. **A3: String-Based Detection** - Could fail on edge cases but mostly works
10. **C1: Heuristic Type Inference** - Works for common cases
11. **B4: Hardcoded Profile Patterns** - Relatively stable configuration

---

## Notes

1. **Remediation already in progress:** The codebase shows evidence of partial remediation:
   - `fhir_schema.py` exists with `FHIRSchemaRegistry` class
   - `profile_registry.py` exists with dynamic profile lookup
   - `status_filter_extractor.py` exists for dynamic status filter extraction
   - `fluent_function_loader.py` exists for dynamic function loading
   - Comments reference "Task B2", "Task C3", etc. from the remediation plan

2. **Fallback patterns:** Many violations include fallback logic that tries dynamic methods first, then falls back to hardcoded values. This is transitional technical debt.

3. **Duplicates:** Some constants appear in multiple files (e.g., BP LOINC codes in both `expressions.py` and `property_scanner.py`).

---

*Audit completed by GLM-5 orchestrator on 2026-03-02*
