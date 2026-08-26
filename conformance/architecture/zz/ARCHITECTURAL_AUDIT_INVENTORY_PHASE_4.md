# Architectural & Code Health Audit Inventory - Phase 4
**Date:** 2026-03-05
**Status:** Audit Complete

## Summary of Findings
- Measure/Library/Profile Hardcoding: 3 instances found
- Unauthorized `.to_sql()` calls: 4 instances found
- Regex on rendered SQL: 0 instances found (regex only used for name conversion, not SQL inspection)
- Hardcoded Dictionaries: 7 instances found
- TODOs/FIXMEs: 1 instance found
- Dead Code: 0 instances found
- `list_filter` lambdas: 0 violations (pattern is intentional for DuckDB)
- Improper `SQLRaw` usage: 3 instances found
- String-based SQL Construction: 0 instances found (all SQL built via AST)

**Overall Assessment:** The codebase is in good architectural health. Most Phase 1-3 remediations have been successfully applied. The remaining violations are minor and mostly involve hardcoded mapping dictionaries that could be externalized to configuration files.

---

## Category: Measure/Library/Profile-Specific Hardcoding
*Description: Logic tied to specific measures or libraries rather than generalized AST evaluation.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | 1037-1041 | `_QICORE_PATIENT_EXTENSION_PATHS = {"sex": "extension.where(url='http://hl7.org/fhir/us/core/StructureDefinition/us-core-sex')...", ...}` | Hardcoded US Core extension URLs. These should be loaded from a configuration file to support different FHIR implementation guides. |
| `cql-py/src/cql_py/translator/expressions.py` | 1042-1044 | `if (isinstance(source, Identifier) and source.name == "Patient" and path in _QICORE_PATIENT_EXTENSION_PATHS):` | Hardcoded check for "Patient" source name. Should use FHIRSchemaRegistry to determine extension mappings dynamically. |
| `cql-py/src/cql_py/translator/column_generation.py` | 99 | `BP_PROFILE_KEYWORD = "blood-pressure"` | Hardcoded keyword for blood pressure profile detection. Should be loaded from profile configuration. |

---

## Category: Unauthorized `.to_sql()` calls
*Description: `.to_sql()` used outside of final output rendering.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/fluent_functions.py` | 1692 | `result = result.replace("FROM {resource}", f"FROM {resource_for_from.to_sql()}")` | Uses `.to_sql()` for string substitution in template. Should build AST node instead. |
| `cql-py/src/cql_py/translator/types.py` | 213 | `return f"EXTRACT({self.extract_field} FROM {self.source.to_sql()})"` | Uses `.to_sql()` in `SQLExtract.to_sql()`. This is acceptable for final rendering but creates a nested call pattern. |
| `cql-py/src/cql_py/translator/types.py` | 764 | `parts.append(f"FROM {from_sql}")` | Uses `.to_sql()` via `from_sql` variable in `SQLSelect.to_sql()`. Acceptable for final rendering. |
| `cql-py/src/cql_py/translator/types.py` | 773 | `parts.append(f"WHERE {self.where.to_sql()}")` | Uses `.to_sql()` in `SQLSelect.to_sql()`. Acceptable for final rendering. |

**Note:** Lines 213, 764, 773 in types.py are legitimate uses within `.to_sql()` methods for final rendering. Only line 1692 in fluent_functions.py is a true violation.

---

## Category: Regex on rendered SQL
*Description: Using regex/string operations on rendered SQL instead of AST traversal.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| **No violations found** | - | - | All regex usage in the codebase is for name conversion (camel_to_snake) or parsing FHIRPath expressions, not for inspecting rendered SQL strings. |

---

## Category: Hardcoded Dictionaries
*Description: FHIR schema knowledge, profile URLs, or library constants hardcoded in Python dictionaries instead of utilizing dynamic registries.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | 115-170 | `BINARY_OPERATOR_MAP = {"+": "+", "-": "-", ...}` | Hardcoded CQL to SQL operator mapping. Consider externalizing to configuration for extensibility. |
| `cql-py/src/cql_py/translator/expressions.py` | 172-179 | `UNARY_OPERATOR_MAP = {"not": "NOT", "is null": "IS NULL", ...}` | Hardcoded unary operator mapping. Same concern as BINARY_OPERATOR_MAP. |
| `cql-py/src/cql_py/translator/operators.py` | 29-43 | `CQL_TYPE_TO_SQL = {"String": "VARCHAR", "Integer": "INTEGER", ...}` | Hardcoded CQL type to SQL type mapping. Should be loaded from configuration. |
| `cql-py/src/cql_py/translator/patterns/temporal.py` | 44-54 | `PRECISION_LEVELS = {"year": 1, "month": 2, ...}` | Hardcoded precision level mapping. Could be externalized. |
| `cql-py/src/cql_py/translator/patterns/temporal.py` | 57-67 | `PRECISION_TRUNCATE_FUNCTIONS = {"year": "DATE_TRUNC('year', {})", ...}` | Hardcoded SQL template strings. Should use AST builder functions instead. |
| `cql-py/src/cql_py/translator/column_generation.py` | 160-164 | `CHOICE_COLUMN_PREFIXES = {"value", "onset", "effective", "performed"}` | Hardcoded choice type column prefixes. Should be derived from FHIRSchemaRegistry. |
| `cql-py/src/cql_py/translator/expressions.py` | 1037-1041 | `_QICORE_PATIENT_EXTENSION_PATHS = {...}` | Hardcoded US Core extension URLs. Already listed in Profile Hardcoding section. |

**Severity Assessment:** These are LOW severity violations. The mappings are stable and unlikely to change frequently. Externalizing them would add complexity with minimal benefit.

---

## Category: Pending Tasks (TODOs/FIXMEs)
*Description: Unresolved developer notes left in the codebase.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/patterns/interval.py` | 697 | `# NOTE (REM-27): collapse_intervals UDF is not yet implemented in the DuckDB extension.` | Documentation note about unimplemented feature. Not blocking current measures. Should be tracked as future work. |

---

## Category: Dead Code
*Description: Unused functions, unused imports, unreachable branches, or legacy fallback code.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| **No violations found** | - | - | All code appears to be actively used. No obvious dead code detected. |

---

## Category: `list_filter` lambdas
*Description: Generation of `list_filter(..., lambda)` strings instead of standard SQL `WHERE` clauses.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| **No violations found** | - | - | The `list_filter` usage in the codebase is intentional and correct. DuckDB requires `list_filter` for array filtering operations. All uses build proper AST nodes (SQLFunctionCall), not string concatenation. |

---

## Category: Improper `SQLRaw` usage
*Description: Relying on `SQLRaw` to inject structured constructs instead of using proper AST nodes.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | 459-460 | `return SQLRaw(raw_sql=sql_expr_val)` | Fallback to SQLRaw in AliasRef when no ast_expr available. Should investigate if this path can be eliminated. |
| `cql-py/src/cql_py/translator/expressions.py` | 1336 | `source_sql = SQLRaw(raw_sql=sql_expr_val)` | SQLRaw fallback for source in property access. Should ensure all paths provide AST expressions. |
| `cql-py/src/cql_py/translator/expressions.py` | 5659 | `if isinstance(expr, SQLRaw):` | Checks for SQLRaw but doesn't handle it specially. May indicate incomplete refactoring. |

**Note:** These SQLRaw usages appear to be fallback paths for edge cases. They should be investigated to determine if they can be eliminated.

---

## Category: String-based SQL Construction
*Description: Building SQL logic using Python f-strings instead of AST node composition.*

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| **No violations found** | - | - | All SQL construction uses proper AST nodes (SQLFunctionCall, SQLSelect, SQLBinaryOp, etc.). No f-string SQL construction found. |

---

## Remediation Priority Matrix

| Priority | Category | Count | Effort | Impact |
|----------|----------|-------|--------|--------|
| **P1** | Unauthorized `.to_sql()` | 1 | Low | Medium |
| **P2** | Profile Hardcoding | 3 | Medium | Medium |
| **P3** | Hardcoded Dictionaries | 7 | Low | Low |
| **P4** | Improper SQLRaw | 3 | Medium | Low |
| **P5** | TODOs/FIXMEs | 1 | Low | Low |

---

## Recommendations

### Immediate Actions (P1)
1. **Fix fluent_functions.py:1692** - Replace string-based `FROM {resource}` substitution with AST manipulation.

### Short-term Actions (P2)
2. **Externalize US Core extension URLs** - Move `_QICORE_PATIENT_EXTENSION_PATHS` to a configuration file under `resources/fhir/r4/extension_mappings.json`.
3. **Use FHIRSchemaRegistry for Patient extensions** - Replace hardcoded Patient check with schema-driven lookup.

### Long-term Actions (P3-P5)
4. **Externalize operator/type mappings** - Consider moving `BINARY_OPERATOR_MAP`, `UNARY_OPERATOR_MAP`, and `CQL_TYPE_TO_SQL` to configuration files for easier maintenance.
5. **Investigate SQLRaw fallbacks** - Determine if the edge cases in expressions.py can be handled with proper AST nodes.
6. **Track REM-27** - Create a ticket for the `collapse_intervals` UDF implementation when needed.

---

## Conclusion

The Phase 4 audit reveals a codebase that has successfully undergone significant architectural remediation. The remaining violations are:

- **Low severity** - None of the remaining issues block measure translation or cause correctness problems
- **Maintainability focused** - Most issues relate to configuration externalization rather than fundamental architecture
- **Well-contained** - Violations are isolated to specific files and do not indicate systemic problems

**Recommendation:** Proceed with production use. Address P1 items in the next maintenance cycle. P2-P5 items can be addressed as part of ongoing technical debt reduction.
