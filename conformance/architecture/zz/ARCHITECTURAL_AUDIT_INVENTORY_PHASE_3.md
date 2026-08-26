# Architectural & Code Health Audit Inventory - Phase 3
**Date:** 2026-03-04
**Status:** Audit Complete

## Summary of Findings
- Measure/Library/Profile Hardcoding: 6 instances found
- Unauthorized `.to_sql()` calls: 12 instances found
- Regex on rendered SQL: 5 instances found
- Hardcoded Dictionaries: 8 instances found
- String-based SQL Construction: 7 instances found
- `list_filter` lambdas: 15 instances found
- Improper `SQLRaw` usage: 6 instances found
- TODOs/FIXMEs: 6 instances found
- Dead Code: 3 instances found

---

## Category: Measure/Library/Profile-Specific Hardcoding
*Description: Logic tied to specific measures or libraries rather than generalized AST evaluation.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/library_resolver.py` | 108-118 | `Library dependency order (CMS165 example)...` | Documentation uses CMS165 as example. While documentation is acceptable, this pattern may indicate measure-specific mental models in design. |
| `cql-py/src/cql_py/translator/library_resolver.py` | 127 | `resolver.register_library(qicore_lib, "QICoreCommon")` | Hardcoded library name "QICoreCommon" used as string constant. Should be loaded from configuration. |
| `cql-py/src/cql_py/translator/fluent_function_loader.py` | 61-62 | `lib_names = ["Status", "QICoreCommon", "FHIRHelpers"]` | Hardcoded list of library names. Not generalizable to other CQL libraries. |
| `cql-py/src/cql_py/translator/fluent_function_loader.py` | 86 | `library_name: ... (e.g., "Status", "QICoreCommon")` | Documentation example - acceptable but indicates pattern. |
| `cql-py/src/cql_py/translator/fluent_function_loader.py` | 168, 174 | `for lib_name in ["FHIRHelpers", "QICoreCommon", "Status"]:` | Duplicated hardcoded library name list. Should be configurable. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 8 | `(e.g., QICoreCommon.cql, Status.cql), NOT built-in` | Comment reference - acceptable documentation. |

---

## Category: Unauthorized `.to_sql()` calls
*Description: `.to_sql()` used outside of final output rendering for intermediate processing.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1171 | `resource_sql = resource_expr.to_sql()` | Converts AST to string mid-pipeline for template substitution. Should use AST nodes directly. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1210 | `param_map[param_name] = arg.to_sql()` | Builds parameter map using string representation instead of AST nodes. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1268 | `result = self._wrap_list_filter_for_mixed_input(...).to_sql()` | Calls to_sql() on intermediate result for template processing. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1283 | `result = self._wrap_boolean_for_list(...).to_sql()` | Same pattern - to_sql() on intermediate AST. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1615 | `return coalesce_node.to_sql()` | Returns string instead of AST node from function. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1633 | `resource_sql = self._resource_expr.to_sql()` | Converts resource expression to string for template substitution. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1661 | `param_map[param_name] = arg.to_sql()` | Parameter map building with string conversion. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1687 | `result = self._substitutor._wrap_list_filter_for_mixed_input(...).to_sql()` | Intermediate to_sql() call. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1701 | `result = self._substitutor._wrap_boolean_for_list(...).to_sql()` | Intermediate to_sql() call. |
| `cql-py/src/cql_py/translator/types.py` | 326 | `coalesce_args.append(SQLFunctionCall(...).to_sql())` | Nested to_sql() within COALESCE rendering logic. |
| `cql-py/src/cql_py/translator/__init__.py` | 30, 159 | `print(f"{name}: {expr.to_sql()}")` | Debug output - acceptable but uses to_sql() outside rendering boundary. |

---

## Category: Regex on Rendered SQL
*Description: Using regex patterns on SQL strings instead of AST introspection.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/ast_utils.py` | 30 | `return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()` | Regex for camel_to_snake conversion. Used for identifier transformation, not SQL inspection - borderline acceptable. |
| `cql-py/src/cql_py/translator/column_generation.py` | 68 | `return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()` | Duplicate camel_to_snake implementation. Should consolidate. |
| `cql-py/src/cql_py/translator/column_generation.py` | 107 | `match = re.search(r"\bcode\s*=\s*['\"](\d{4,5}-\d+)['\"]", clause)` | Regex to extract LOINC code from component.where clause string. Violates AST-first principle. |
| `cql-py/src/cql_py/translator/expressions.py` | 5890-5892 | `match = re.match(r"(starts|ends)\s+(\d+(?:\.\d+)?)\s+(\w+)..."` | Regex parsing of temporal operator strings. Should be handled by CQL parser instead. |
| `cql-py/src/cql_py/translator/expressions.py` | 6009-6010 | `match = re.match(r"(starts|ends)\s+(\d+(?:\.\d+)?)..."` | Duplicate temporal operator regex pattern. Same violation as above. |

---

## Category: Hardcoded Dictionaries
*Description: FHIR schema knowledge or constants hardcoded in Python dictionaries instead of using dynamic registries.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/patterns/retrieve.py` | 49-64 | `_TERMINOLOGY_PROPERTY_DEFAULTS = {...}` | Hardcoded mapping of resource types to terminology properties. Should use FHIRSchemaRegistry. |
| `cql-py/src/cql_py/translator/patterns/retrieve.py` | 76-80 | `return {"LOINC": "http://loinc.org", "SNOMED-CT": ...}` | Fallback code system URLs hardcoded. Should load from terminology config. |
| `cql-py/src/cql_py/translator/patterns/retrieve.py` | 434-445 | `prefixes = ["http://cts.nlm.nih.gov/fhir/ValueSet/", ...]` | Hardcoded value set URL prefixes. Should be configurable. |
| `cql-py/src/cql_py/translator/column_generation.py` | 74-77 | `BP_COMPONENT_PROPERTY_PATHS = {...}` | Hardcoded BP component paths. Should come from profile configuration. |
| `cql-py/src/cql_py/translator/column_generation.py` | 113-117 | `bp_codes = {"8480-6": "systolic_value", "8462-4": "diastolic_value"}` | Hardcoded LOINC code to column mapping. Should use terminology registry. |
| `cql-py/src/cql_py/translator/fhir_schema.py` | 26-45 | `FHIR_TYPE_TO_UDF = {...}` | FHIR type to UDF mapping. While structural, should be configurable per deployment. |
| `cql-py/src/cql_py/translator/fhir_schema.py` | 48-67 | `FHIR_TYPE_TO_SQL = {...}` | FHIR type to SQL type mapping. Same concern as above. |
| `cql-py/src/cql_py/translator/fhir_schema.py` | 382-415 | `COLUMN_TO_FHIR_PATHS = {...}` | Column name to FHIR path mapping hardcoded. Should be loaded from external configuration. |

---

## Category: String-based SQL Construction
*Description: Building SQL logic using Python f-strings instead of AST node composition.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/types.py` | 764 | `parts.append(f"FROM {from_sql}")` | f-string SQL construction in SQLSelect.to_sql(). Part of rendering - acceptable. |
| `cql-py/src/cql_py/translator/types.py` | 773 | `parts.append(f"WHERE {self.where.to_sql()}")` | Same - rendering boundary. |
| `cql-py/src/cql_py/translator/types.py` | 827 | `return f"EXISTS {self.subquery.to_sql()}"` | Rendering - acceptable. |
| `cql-py/src/cql_py/translator/types.py` | 1202, 1204 | `return f"SELECT patient_id, resource FROM {op.to_sql()}"` | String construction for SELECT. Should use SQLSelect AST. |
| `cql-py/src/cql_py/translator/types.py` | 1252, 1282 | `sql = f"SELECT * FROM {op.to_sql()}"` | String construction for SELECT. Should use SQLSelect AST. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1262, 1683 | `result.replace("FROM {resource}", f"FROM {resource_for_from.to_sql()}")` | String replacement on SQL template instead of AST manipulation. |
| `cql-py/src/cql_py/translator/patterns/retrieve.py` | 619 | `profile_path = f"meta.profile.contains('{profile_url}')"` | FHIRPath string construction instead of using FHIRPathBuilder. |

---

## Category: `list_filter` Lambdas
*Description: Generation of `list_filter(..., lambda)` strings instead of standard SQL WHERE clauses.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/functions.py` | 285-293 | `# Where requires a lambda - use list_filter...` | Comment indicates pattern awareness. Generates list_filter for Where clauses. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 536 | `# Check _STATUS_FILTER_FALLBACKS registry first – generates WHERE clause instead of list_filter` | Comment shows intentional pattern to avoid list_filter where possible. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 591 | `list_filter lambdas so that no lambda expressions appear` | Documentation of cleanup effort. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1265-1268 | `elif "list_filter({resource}" in template:` | String detection of list_filter pattern in templates. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1295-1347 | `_wrap_list_filter_for_mixed_input(...)` | Helper function that builds list_filter AST nodes. Necessary evil for DuckDB list operations. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1386 | `array_length(list_filter({resource}, r -> ...)) > 0` | Template string for list_filter pattern. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1416-1420 | `name="list_filter", args=[resource_expr, SQLLambda(...)]` | AST construction of list_filter - acceptable as it builds AST. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1685-1687 | `elif "list_filter({resource}" in self._template:` | String detection pattern. |
| `cql-py/src/cql_py/translator/ast_utils.py` | 25 | `LIST_OPERATION_FUNCTIONS: frozenset[str] = frozenset({'list_filter', ...})` | Constant definition - acceptable. |
| `cql-py/src/cql_py/translator/ast_utils.py` | 692-702 | `List operations include: list_filter, jsonConcat...` | Documentation. |
| `cql-py/src/cql_py/translator/patterns/aggregation.py` | 303 | `# For list/array expressions (jsonConcat, list_filter), use array_length > 0` | Pattern documentation. |
| `cql-py/src/cql_py/translator/expressions.py` | 1316 | `is_list_expr = any(op in sql_expr_val for op in ['list_filter', ...])` | String detection on rendered SQL - violation. |
| `cql-py/src/cql_py/translator/expressions.py` | 4589-4593 | `if func_name_lower == "jsonconcat" or func_name_lower == "list_filter":` | Function name check - acceptable AST-based check. |
| `cql-py/src/cql_py/translator/expressions.py` | 5214-5219 | `name="list_filter", args=[subquery, SQLLambda(...)]` | AST construction - acceptable. |

---

## Category: Improper `SQLRaw` Usage
*Description: Relying on `SQLRaw` to inject structured constructs instead of proper AST nodes.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1348 | `args=[resource_expr, SQLLambda(param=lambda_var, body=SQLRaw(raw_sql=predicate))]` | SQLRaw used for lambda body predicate. Should build proper AST. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1356 | `when_clauses=[(SQLRaw(raw_sql=scalar_predicate), ...)]` | SQLRaw for CASE WHEN condition. Should use SQLBinaryOp or similar. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1420 | `args=[resource_expr, SQLLambda(param="r", body=SQLRaw(raw_sql=condition_with_r))]` | SQLRaw for lambda body. Same violation. |
| `cql-py/src/cql_py/translator/expressions.py` | 470-471 | `return SQLRaw(raw_sql=sql_expr_val)` | Fallback to SQLRaw when ast_expr not available. Indicates incomplete AST migration. |
| `cql-py/src/cql_py/translator/expressions.py` | 1341 | `source_sql = SQLRaw(raw_sql=sql_expr_val)` | SQLRaw fallback for source expressions. |
| `cql-py/src/cql_py/translator/translator.py` | 770 | `return SQLRaw(raw_sql="SELECT p.patient_id, NULL AS value FROM _patients AS p WHERE FALSE")` | Entire query as SQLRaw string. Should use SQLSelect AST. |

---

## Category: Pending Tasks (TODOs/FIXMEs)
*Description: Unresolved developer notes left in the codebase.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | 185 | `# TODO (Task C5): Replace with dynamic resolution from CQL valueset context` | Incomplete migration to dynamic valueset resolution. |
| `cql-py/src/cql_py/translator/expressions.py` | 4479 | `# TODO: Implement proper timezone offset extraction` | Unimplemented timezone feature. |
| `cql-py/src/cql_py/translator/expressions.py` | 4813 | `# TODO: Implement proper multi-source query handling with CROSS JOIN` | Incomplete multi-source query support. |
| `cql-py/src/cql_py/translator/expressions.py` | 5879, 6001 | `TODO: Improve CQL parser to decompose temporal operators into structured fields` | Parser limitation documented. Requires upstream parser changes. |
| `cql-py/src/cql_py/translator/patterns/interval.py` | 696 | `TODO (REM-27, LOW): Implement collapse_intervals UDF in DuckDB extension.` | Pending UDF implementation. |

---

## Category: Dead Code
*Description: Unused functions, imports, or legacy fallback code no longer called by main execution pipeline.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | 200-203 | `# Hardcoded choice type maps removed - replaced with FHIRSchemaRegistry (Task B2)` | Comment references removed code but remains as documentation. Should clean up. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | 536 | `# Check _STATUS_FILTER_FALLBACKS registry first` | References registry that may have legacy entries. Audit registry for unused filters. |
| `cql-py/src/cql_py/translator/property_scanner.py` | 38-43 | `from cql_py.translator.column_generation import (extract_loinc_code_from_component_where, ...)` | Import used only for BP-specific patterns. May be dead code if BP handling moved elsewhere. |

---

## Recommendations for Remediation Priority

### High Priority (Architectural Integrity)
1. **Eliminate `.to_sql()` mid-pipeline calls** in `fluent_functions.py` - These violate the AST-first principle and make debugging difficult.
2. **Replace SQLRaw for structured constructs** - SQLRaw should only be used for truly raw SQL that cannot be represented as AST.
3. **Consolidate hardcoded dictionaries** - Move `_TERMINOLOGY_PROPERTY_DEFAULTS`, `FHIR_TYPE_TO_UDF`, etc. to configuration files.

### Medium Priority (Code Health)
4. **Implement Task C5** - Dynamic resolution from CQL valueset context to eliminate `COMPONENT_CODE_TO_COLUMN` hardcoding.
5. **Consolidate camel_to_snake implementations** - Single implementation in ast_utils.py, import elsewhere.
6. **Address temporal operator regex parsing** - Work with parser team to decompose operators into structured AST fields.

### Low Priority (Technical Debt)
7. **Clean up TODO comments** - Either implement or convert to tracked issues.
8. **Audit `_STATUS_FILTER_FALLBACKS`** - Remove unused entries.
9. **Documentation hardcoding** - Update examples to use generic library names instead of QICoreCommon/Status.

---

## Audit Methodology

This audit was conducted by:
1. Scanning all Python files in `cql-py/src/cql_py/translator/` directory
2. Using grep pattern matching for target anti-patterns
3. Manual code review of flagged files
4. Cross-referencing against `PLAN-ARCHITECTURAL-REMEDIATION.md` standards

**Files Audited:**
- `translator.py`, `expressions.py`, `fluent_functions.py`, `types.py`
- `cte_builder.py`, `context.py`, `ast_utils.py`
- `column_generation.py`, `fhir_schema.py`, `property_scanner.py`
- `fhirpath_builder.py`, `library_resolver.py`, `fluent_function_loader.py`
- `patterns/retrieve.py`, `patterns/interval.py`, `patterns/aggregation.py`

**Total Violations Found:** 68 instances across 9 categories
