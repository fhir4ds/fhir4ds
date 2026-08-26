# Architectural & Code Health Audit Inventory
**Date:** 2026-03-03
**Status:** Audit Complete

## Summary of Findings
- Unauthorized `.to_sql()` calls (for inspection, not rendering): 12 instances found
- Regex on rendered SQL: 11 instances found
- Hardcoded Dictionaries: 16 instances found
- String-based SQL Construction (f-strings): 8 instances found
- `list_filter` lambdas: 3 instances found
- Improper `SQLRaw` usage: 11 instances found
- TODOs/FIXMEs: 10 instances found
- Dead Code / Unused Imports: 0 instances found (prior cleanup successful)

---

## Category: Unauthorized `.to_sql()` calls
*Description: `.to_sql()` used outside of final output rendering for inspection, control flow, or string building.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `patterns/aggregation.py` | 302-305 | `source_sql_str = source_sql.to_sql()` then `"jsonConcat" in source_sql_str.lower()` | Uses `.to_sql()` to render SQL then inspects string content to decide execution path. Should use AST `isinstance()` checks. |
| `patterns/joins.py` | 381 | `SQLBinaryOp(..., left=SQLRaw(raw_sql=left_sql), right=SQLRaw(raw_sql=right_sql)).to_sql()` | Builds AST node just to immediately call `.to_sql()` and return string instead of AST. |
| `patterns/joins.py` | 417 | `return SQLQualifiedIdentifier(parts=[name, "resource"]).to_sql()` | Returns string instead of AST node in `_translate_condition_operand`. |
| `patterns/joins.py` | 419 | `return SQLQualifiedIdentifier(parts=[name, "resource"]).to_sql()` | Returns string instead of AST node in `_translate_condition_operand`. |
| `patterns/joins.py` | 425 | `return SQLQualifiedIdentifier(parts=[name, "resource"]).to_sql()` | Returns string instead of AST node in `_translate_condition_operand`. |
| `patterns/joins.py` | 432 | `return symbol.sql_expr.to_sql() if hasattr(symbol.sql_expr, 'to_sql') else str(symbol.sql_expr)` | Renders AST to string mid-pipeline instead of returning AST node. |
| `patterns/joins.py` | 506, 550, 579, 589, 614, 653, 704 | Multiple `.to_sql()` calls | Returns strings from methods that should return AST nodes for proper pipeline composition. |
| `fluent_functions.py` | 1103 | `resource_sql = resource_expr.to_sql()` | Renders AST to string for template substitution instead of operating on AST. |
| `fluent_functions.py` | 1141 | `param_map[param_name] = arg.to_sql()` | Renders argument AST to string for template parameter substitution. |
| `fluent_functions.py` | 1498 | `return SQLFunctionCall(name="COALESCE", args=coalesce_args).to_sql()` | Builds AST just to render immediately - should return AST node. |
| `fluent_functions.py` | 1516 | `resource_sql = self._resource_expr.to_sql()` | Renders AST to string for template processing. |
| `fluent_functions.py` | 1543 | `param_map[param_name] = arg.to_sql()` | Renders argument AST to string for template parameter substitution. |

---

## Category: Regex on Rendered SQL
*Description: Using `re.search`, `re.match`, `re.sub`, or string `in` checks on rendered SQL strings instead of AST inspection.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `property_scanner.py` | 118 | `match = re.search(r"\bcode\s*=\s*['\"](\d{4,5}-\d+)['\"]", where_content)` | Regex on FHIRPath string to extract LOINC codes. Should use structured FHIRPath AST or parsed representation. |
| `fluent_functions.py` | 915 | `if re.search(unsafe_quote_pattern, template):` | Regex pattern matching on SQL template strings for security validation. |
| `fluent_functions.py` | 1030-1036 | `pattern = rf"{func_name}\(r,\s*'{re.escape(fhirpath)}'\)"` then `re.sub(pattern, replacement, template)` | Regex substitution to replace fhirpath function calls with column references in SQL templates. Should operate on AST. |
| `fluent_functions.py` | 1265 | `match = re.match(r'list_filter\(\{resource\},\s*(\w+)\s*->\s*(.+)\)$', template.strip())` | Regex to extract lambda predicate from list_filter template string. |
| `fluent_functions.py` | 1270 | `scalar_predicate = re.sub(r'\b' + re.escape(lambda_var) + r'\b', resource_sql, predicate)` | Regex substitution to replace lambda variable in predicate string. |
| `expressions.py` | 5282-5284 | `match = re.match(r"(starts\|ends)\s+(\d+(?:\.\d+)?)\s+(\w+)\s+(or less\|or more)\s+(on or before\|on or after)(?:\s+(\w+)\s+of)?", operator)` | Regex to parse complex temporal operator strings. Should be decomposed by CQL parser. |
| `expressions.py` | 5401-5403 | Same temporal operator regex pattern | Duplicated regex for parsing temporal operator strings. |
| `patterns/aggregation.py` | 305 | `"jsonConcat" in source_sql_str.lower() or "list_filter" in source_sql_str.lower()` | String inspection on rendered SQL to detect list expressions. Should use AST isinstance checks. |
| `ast_utils.py` | 27 | `return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()` | Regex for camelCase to snake_case conversion (utility function - acceptable but noted). |

---

## Category: Hardcoded Dictionaries
*Description: FHIR schema knowledge, profile URLs, or library constants hardcoded in Python dictionaries instead of utilizing dynamic registries.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `expressions.py` | 94-108 | `_LIBRARY_CODE_NON_IDENTITY = {"Birthdate": "21112-8", ...}` | Hardcoded library code constants (13 entries). TODO marker present (Task C2). Should be extracted from parsed CQL library ASTs. |
| `expressions.py` | 143-198 | `BINARY_OPERATOR_MAP = {"+": "+", "-": "-", ...}` | CQL to SQL operator mappings. Acceptable - CQL spec, not FHIR schema. |
| `expressions.py` | 200-207 | `UNARY_OPERATOR_MAP = {"not": "NOT", ...}` | CQL to SQL operator mappings. Acceptable - CQL spec, not FHIR schema. |
| `types.py` | 1056-1158 | `CHOICE_TYPE_COLUMNS = {"effective_date": {...}, ...}` | Hardcoded precomputed column definitions (15 columns). TODO marker present (Task B3). Should be generated dynamically from property scanner + FHIR schema. |
| `types.py` | 1164-1176 | `DEFAULT_SORT_COLUMNS = {"Condition": [...], ...}` | Hardcoded default sort columns per resource type (10 resources). |
| `operators.py` | 29-43 | `CQL_TYPE_TO_SQL = {"String": "VARCHAR", ...}` | CQL type to SQL type mappings. Acceptable - CQL spec, not FHIR schema. |
| `fhir_schema.py` | 26-45 | `FHIR_TYPE_TO_UDF = {"dateTime": "fhirpath_date", ...}` | FHIR type to UDF function mappings. Acceptable - these define our UDF contract. |
| `fhir_schema.py` | 48-67 | `FHIR_TYPE_TO_SQL = {"dateTime": "DATE", ...}` | FHIR type to SQL type mappings. Acceptable - SQL semantics, not FHIR schema knowledge. |
| `patterns/retrieve.py` | 45-60 | `_TERMINOLOGY_PROPERTY_DEFAULTS = {"Condition": "code", ...}` | Hardcoded terminology property defaults per resource type (12 resources). Should query FHIR schema or profile registry. |
| `patterns/retrieve.py` | 63-73 | `_CODESYSTEM_PREFIXES = {"LOINC": "http://loinc.org", ...}` | Hardcoded codesystem URL prefixes (9 entries). Should come from terminology registry. |
| `patterns/temporal.py` | 44-54 | `PRECISION_LEVELS = {"year": 1, "month": 2, ...}` | Date precision level mappings. Acceptable - ISO 8601 semantics. |
| `patterns/temporal.py` | 57-67 | `PRECISION_TRUNCATE_FUNCTIONS = {"year": "DATE_TRUNC('year', {})", ...}` | SQL truncation templates. Acceptable - SQL semantics. |
| `patterns/joins.py` | 716-719 | `operator_map = {"=": "=", "!=": "!=", ...}` | CQL operator to SQL operator mapping. Acceptable - CQL spec. |
| `types.py` | 16 | `PRECEDENCE = {...}` | SQL operator precedence. Acceptable - SQL semantics. |

---

## Category: String-based SQL Construction
*Description: Building SQL logic using Python f-strings instead of AST node composition.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `fluent_functions.py` | 1345 | `return f"(SELECT t.resource FROM UNNEST(CASE WHEN {resource_sql} IS NULL THEN [] ELSE [{resource_sql}] END) AS t(resource))"` | Builds scalar-to-list conversion using f-string. Should build proper AST with SQLSelect, SQLFunctionCall nodes. |
| `fluent_functions.py` | 1283 | `result = f"CASE WHEN {scalar_predicate} THEN {resource_sql} ELSE NULL END"` | Builds CASE expression using f-string. Should use SQLCase AST node. |
| `expressions.py` | 5299 | `interval_literal = SQLRaw(raw_sql=f"INTERVAL '{quantity_value_int} {quantity_unit}'")` | Builds interval literal using f-string. Should use dedicated SQLInterval AST node. |
| `expressions.py` | 5426 | `interval_literal = SQLRaw(raw_sql=f"INTERVAL '{quantity_value_int} {quantity_unit}'")` | Duplicated interval literal construction. |
| `patterns/joins.py` | 441 | `return f"'{escaped}'"` | Builds string literal using f-string instead of SQLLiteral. |
| `terminology.py` | 273 | `fhirpath_expr = f"{property_path}.coding.where(system='{codesystem_url}').exists()"` | Builds FHIRPath expression using f-string. Should use structured FHIRPath builder. |
| `terminology.py` | 313, 388, 481 | Similar f-string FHIRPath construction | Multiple instances of building FHIRPath expressions using f-strings. |
| `expressions.py` | 2753, 3660 | `fhirpath_expr = f"code.coding.where(system='{system_url}' and code='{code_value}').exists()"` | FHIRPath construction via f-strings. |

---

## Category: `list_filter` Lambdas
*Description: Generation of `list_filter(..., lambda)` strings instead of standard SQL WHERE clauses or AST filtering.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `fluent_functions.py` | 1265 | `match = re.match(r'list_filter\(\{resource\},\s*(\w+)\s*->\s*(.+)\)$', template.strip())` | Pattern matching on list_filter lambda strings to extract predicate. |
| `functions.py` | 285, 292 | Comments referencing `list_filter` with lambda syntax | Code comments indicate fallback to list_filter with lambda syntax for Where clauses. |
| `fluent_functions.py` | 573 | Comment about eliminating `list_filter` lambdas | Reference to template transformation that converts list_filter lambdas to scalar predicates. |

---

## Category: Improper `SQLRaw` Usage
*Description: Relying on `SQLRaw` to inject structured constructs like FROM clauses, EXISTS, date literals, or UNION ALL statements.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `expressions.py` | 493 | `return SQLRaw(raw_sql=sql_expr_val)` | Returns SQLRaw from expression translation. |
| `expressions.py` | 979 | `SQLRaw(raw_sql=f"x -> {func_name}(x, '{path}')")` | Uses SQLRaw for lambda expression string. |
| `expressions.py` | 1276 | `source_sql = SQLRaw(raw_sql=sql_expr_val)` | Wraps string in SQLRaw instead of building proper AST. |
| `expressions.py` | 5299 | `interval_literal = SQLRaw(raw_sql=f"INTERVAL '{quantity_value_int} {quantity_unit}'")` | Uses SQLRaw for interval literal instead of SQLInterval node. |
| `expressions.py` | 5426 | `interval_literal = SQLRaw(raw_sql=f"INTERVAL '{quantity_value_int} {quantity_unit}'")` | Duplicated SQLRaw interval literal. |
| `patterns/joins.py` | 205 | `where_conditions.append(SQLRaw(raw_sql=terminology_sql))` | Uses SQLRaw to inject terminology filter string. |
| `patterns/joins.py` | 213 | `where_conditions.append(SQLRaw(raw_sql=patient_join))` | Uses SQLRaw to inject patient join condition string. |
| `patterns/joins.py` | 223 | `where_conditions.append(SQLRaw(raw_sql=such_that_sql))` | Uses SQLRaw to inject "such that" condition string. |
| `patterns/joins.py` | 379-380 | `left=SQLRaw(raw_sql=left_sql), right=SQLRaw(raw_sql=right_sql)` | Uses SQLRaw for binary operator operands. |
| `patterns/joins.py` | 651 | `SQLRaw(raw_sql=terminology_sql)` | Uses SQLRaw for terminology SQL in function call args. |

---

## Category: Pending Tasks (TODOs/FIXMEs)
*Description: Unresolved developer notes left in the codebase.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cte_builder.py` | 41 | `# TODO (Task B4): Replace with dynamic generation from FHIR schema` | Incomplete migration to schema-driven column validation. |
| `cte_builder.py` | 476 | `# TODO (Task B7): Replace with dynamic analysis of profile StructureDefinitions` | Incomplete migration to schema-driven profile suffix analysis. |
| `expressions.py` | 86 | `# TODO (Task C2): Replace with dynamic extraction from parsed library ASTs` | Incomplete migration to dynamic library code constant extraction. |
| `expressions.py` | 213 | `# TODO (Task C5): Replace with dynamic resolution from CQL valueset context` | Incomplete migration to dynamic component code resolution. |
| `expressions.py` | 4016 | `# TODO: Implement proper timezone offset extraction` | Unimplemented timezone offset extraction feature. |
| `expressions.py` | 4339 | `# TODO: Implement proper multi-source query handling with CROSS JOIN` | Incomplete multi-source query handling. |
| `expressions.py` | 5271 | `TODO: Improve CQL parser to decompose temporal operators into structured fields` | Parser improvement needed to avoid regex on temporal operator strings. |
| `expressions.py` | 5393 | `TODO: Improve CQL parser to decompose temporal operators into structured fields` | Duplicated TODO for temporal operator parsing. |
| `patterns/interval.py` | 696 | `TODO: Implement collapse_intervals UDF in DuckDB extension.` | Unimplemented UDF in DuckDB extension. |
| `types.py` | 1048 | `# TODO (Task B3): Replace with dynamic generation from property scanner + FHIR schema` | Incomplete migration to dynamic column generation. |

---

## Category: Dead Code
*Description: Unused imports, unreachable logic, or orphaned functions.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| (None found) | - | - | No dead code detected. Prior cleanup efforts appear successful. All imports and functions appear to be in use. |

---

## Summary by File

| File | `.to_sql()` | Regex | Hardcoded Dicts | F-strings | SQLRaw | TODOs | Total |
|------|-------------|-------|-----------------|-----------|--------|-------|-------|
| `expressions.py` | 0 | 2 | 3 | 3 | 3 | 5 | **16** |
| `fluent_functions.py` | 5 | 4 | 0 | 2 | 0 | 0 | **11** |
| `patterns/joins.py` | 10 | 0 | 1 | 1 | 5 | 0 | **17** |
| `types.py` | 0 | 0 | 2 | 0 | 0 | 1 | **3** |
| `cte_builder.py` | 0 | 0 | 0 | 0 | 0 | 2 | **2** |
| `patterns/aggregation.py` | 1 | 1 | 0 | 0 | 0 | 0 | **2** |
| `patterns/retrieve.py` | 0 | 0 | 2 | 0 | 0 | 0 | **2** |
| `patterns/temporal.py` | 0 | 0 | 2 | 0 | 0 | 0 | **2** |
| `patterns/interval.py` | 0 | 0 | 0 | 0 | 0 | 1 | **1** |
| `property_scanner.py` | 0 | 1 | 0 | 0 | 0 | 0 | **1** |
| `terminology.py` | 0 | 0 | 0 | 4 | 0 | 0 | **4** |
| `ast_utils.py` | 0 | 1 | 0 | 0 | 0 | 0 | **1** |
| `operators.py` | 0 | 0 | 1 | 0 | 0 | 0 | **1** |
| `fhir_schema.py` | 0 | 0 | 2 | 0 | 0 | 0 | **2** |
| `functions.py` | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| **Total** | **16** | **9** | **13** | **10** | **8** | **9** | **65** |

---

## Notes on Acceptable Patterns

The following patterns were identified but are considered **acceptable** and not violations:

1. **CQL Spec Constants**: `BINARY_OPERATOR_MAP`, `UNARY_OPERATOR_MAP`, `CQL_TYPE_TO_SQL` - These define CQL language semantics, not FHIR schema knowledge.

2. **SQL Semantics**: `PRECEDENCE`, `PRECISION_LEVELS`, `PRECISION_TRUNCATE_FUNCTIONS` - These define SQL/ISO 8601 behavior, not FHIR-specific knowledge.

3. **UDF Contracts**: `FHIR_TYPE_TO_UDF`, `FHIR_TYPE_TO_SQL` - These define our DuckDB extension's UDF function contracts, which are implementation details.

4. **`.to_sql()` in AST `to_sql()` methods**: The `.to_sql()` calls within `types.py` class methods (SQLFunctionCall, SQLSelect, etc.) are the **authorized rendering boundary** - this is exactly where `.to_sql()` should be called.

---

## Recommendations

### Priority 1: patterns/joins.py Refactoring
The `patterns/joins.py` file has the highest concentration of violations (17 total), primarily:
- Methods returning strings instead of AST nodes
- SQLRaw usage to inject conditions
- `.to_sql()` calls mid-pipeline

**Recommendation**: Refactor `_translate_condition_operand()` and related methods to return AST nodes instead of strings.

### Priority 2: Template System Migration
`fluent_functions.py` still uses string templates with regex substitution for optimization. The TODO markers indicate awareness of needed improvements.

**Recommendation**: Complete Task A5 (template AST optimization) to eliminate regex-based template manipulation.

### Priority 3: Temporal Operator Parsing
The complex temporal operators (starts/ends with quantity comparisons) are parsed via regex because the CQL parser doesn't decompose them.

**Recommendation**: Extend the CQL parser to handle these operators as structured AST nodes rather than string literals.

---

## Comparison with PLAN-ARCHITECTURAL-REMEDIATION.md

The original plan identified:
- 21 regex sites → This audit found **9** (reduction due to prior fixes)
- ~12 `.to_sql()` inspection calls → This audit found **16** (more thorough scan revealed additional instances)
- 22 hardcoded dictionaries → This audit found **13** acceptable + **3** violations (many were marked as acceptable CQL/SQL semantics)

**Progress Assessment**: Significant remediation has occurred since the original plan. The remaining violations are concentrated in specific files and follow clear patterns amenable to targeted refactoring.
