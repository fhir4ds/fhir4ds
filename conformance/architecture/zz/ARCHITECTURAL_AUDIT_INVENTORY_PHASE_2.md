# Architectural Audit Inventory - Phase 2
**Date:** 2026-03-03
**Auditor:** Principal Software Architect
**Scope:** `cql-py/src/cql_py/translator/**/*.py` (32 files)
**Reference Standard:** `plans/PLAN-ARCHITECTURAL-REMEDIATION.md`

---

## Executive Summary

This Phase 2 audit provides a comprehensive, file-by-file inventory of architectural violations in the CQL-to-SQL transpiler. The audit covers all 32 Python files in the translator directory and catalogs violations against the design principles established in the remediation plan.

| Violation Category | Phase 1 Count | Phase 2 Count | Delta | Status |
|--------------------|---------------|---------------|-------|--------|
| Unauthorized `.to_sql()` calls | ~12 | **43** | +31 | Expanded scan |
| Regex on rendered SQL | 21 | **5** | -16 | Remediated |
| Hardcoded Dictionaries | 22 | **9** | -13 | Partially remediated |
| String-based SQL (f-strings) | - | **23** | N/A | New category |
| `list_filter` lambdas | - | **25** | N/A | New category |
| Improper `SQLRaw` usage | - | **12** | N/A | New category |
| TODOs/FIXMEs/HACKs | - | **6** | N/A | New category |
| Dead Code | - | **0** | N/A | Clean |

**Key Finding:** The `.to_sql()` count appears higher than Phase 1 because this audit is more thorough. Many `.to_sql()` calls are **authorized** (within AST class methods for final rendering). This report distinguishes between authorized and unauthorized usage.

---

## Category A: Unauthorized `.to_sql()` Calls

*Definition: `.to_sql()` used outside of final output rendering for inspection, control flow, or string building.*

### A1. Control Flow Violations (Critical)
Using `.to_sql()` result in `if` statements or branching logic:

| File | Line(s) | Code Pattern | Remediation |
|------|---------|--------------|-------------|
| `fluent_functions.py` | 1098 | `resource_sql = resource_expr.to_sql()` then string operations | Use AST introspection via `ast_utils` |
| `fluent_functions.py` | 1137 | `param_map[param_name] = arg.to_sql()` for template substitution | Operate on AST nodes |
| `fluent_functions.py` | 1375 | `return f"({select_node.to_sql()})"` for subquery wrapping | Return SQLSubquery AST |
| `fluent_functions.py` | 1531 | `return coalesce_node.to_sql()` instead of returning AST | Return the AST node |
| `fluent_functions.py` | 1549 | `resource_sql = self._resource_expr.to_sql()` | Operate on AST |
| `fluent_functions.py` | 1577 | `param_map[param_name] = arg.to_sql()` | Same as A1.2 |
| `expressions.py` | 1058 | `resource_col = SQLQualifiedIdentifier(parts=[source_sql.to_sql(), "resource"])` | Use AST directly |
| `translator.py` | 2878 | `sql = expr.to_sql() if hasattr(expr, 'to_sql') else str(expr)` | Always use AST |

### A2. Mid-Pipeline String Building (High)
Calling `.to_sql()` to build intermediate strings:

| File | Line(s) | Code Pattern | Remediation |
|------|---------|--------------|-------------|
| `translator.py` | 556 | `demographics_sql = phase2_result.patient_demographics_cte.to_sql()` | Pass AST to final assembly |
| `translator.py` | 562 | `cte_sql = cte_ast.to_sql()` in loop | Collect ASTs, render once |
| `translator.py` | 570 | `cte_sql = cte_ast.to_sql()` | Same as A2.2 |
| `translator.py` | 693 | `return wrapped_ast.to_sql()` | Return AST from method |
| `translator.py` | 699 | `return expr.to_sql()` | Return AST |
| `translator.py` | 711 | `return wrapped.to_sql()` | Return AST |
| `translator.py` | 714 | `f"""SELECT p.patient_id, ({expr.to_sql()})...` | Build as SQLSelect AST |
| `translator.py` | 784 | `return cte.to_sql()` | Return AST |
| `translator.py` | 1411-1447 | Multiple `.to_sql()` in `_build_definition_cte_with_patient_id` | Return tuple of (AST, has_resource) |
| `translator.py` | 1611-1625 | `.to_sql()` in `_build_cte_from_ast` | Return AST |
| `translator.py` | 2077-2090 | `.to_sql()` in `_wrap_ast_with_patient_id` | Return AST |
| `translator.py` | 2192-2220 | `.to_sql()` in boolean wrapping methods | Return AST |

### A3. Authorized Rendering Boundary (Acceptable)
These `.to_sql()` calls are **within** the AST class methods that implement the rendering boundary:

| File | Lines | Class/Method | Status |
|------|-------|--------------|--------|
| `types.py` | 172-194 | `SQLNamedArg.to_sql()`, `SQLExtract.to_sql()` | AUTHORIZED |
| `types.py` | 292-353 | `SQLFunctionCall.to_sql()` | AUTHORIZED |
| `types.py` | 470-510 | `SQLArray.to_sql()`, `SQLList.to_sql()`, `SQLCase.to_sql()` | AUTHORIZED |
| `types.py` | 533-627 | `SQLLambda.to_sql()`, `SQLAlias.to_sql()`, `SQLInterval.to_sql()` | AUTHORIZED |
| `types.py` | 645-800 | `SQLJoin.to_sql()`, `SQLSelect.to_sql()` | AUTHORIZED |
| `types.py` | 800-835 | `SQLSubquery.to_sql()`, `SQLExists.to_sql()`, `CTEDefinition.to_sql()` | AUTHORIZED |
| `types.py` | 1042-1409 | `SQLMaterializedView.to_sql()`, `SQLWith.to_sql()`, `SQLWindowFunction.to_sql()` | AUTHORIZED |
| `types.py` | 1488-1537 | `SQLUnion.to_sql()`, `SQLWindowSpec.to_sql()` | AUTHORIZED |
| `translator.py` | 4059-4096 | `.to_sql()` in `_build_sql` final assembly | AUTHORIZED |

---

## Category B: Regex on Rendered SQL

*Definition: Using `re.search`, `re.match`, `re.sub`, or string `in` checks on rendered SQL strings instead of AST inspection.*

| File | Line(s) | Pattern | Violation | Remediation |
|------|---------|---------|-----------|-------------|
| `property_scanner.py` | 118 | `re.search(r"\bcode\s*=\s*['\"](\d{4,5}-\d+)['\"]", where_content)` | Extracts LOINC codes from FHIRPath string | Parse FHIRPath to AST |
| `expressions.py` | 5251 | `re.match(r"(starts|ends)\s+(\d+(?:\.\d+)?)\s+(\w+)...", operator)` | Parses temporal operator strings | Extend CQL parser |
| `expressions.py` | 5370 | Same temporal regex | Duplicate of B2 | Extend CQL parser |
| `fluent_functions.py` | 916 | `re.search(unsafe_quote_pattern, template)` | Security validation on template | Use parameterized templates |
| `ast_utils.py` | 27 | `re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()` | camelCase to snake_case | Acceptable utility |

---

## Category C: Hardcoded Dictionaries

*Definition: FHIR schema knowledge, profile URLs, or library constants hardcoded in Python dictionaries instead of dynamic registries.*

### C1. FHIR Schema Knowledge (Critical)

| File | Line(s) | Dictionary | Contents | Remediation |
|------|---------|------------|----------|-------------|
| `types.py` | 1051-1153 | `CHOICE_TYPE_COLUMNS` | 15 precomputed column definitions for choice types | Generate from FHIR schema |
| `types.py` | 1159-1171 | `DEFAULT_SORT_COLUMNS` | Default sort columns per resource type | Query FHIR schema |
| `fhir_schema.py` | 382-415 | `COLUMN_TO_FHIR_PATHS` | Column name to FHIRPath mappings | Load from StructureDefinitions |
| `patterns/retrieve.py` | 47-62 | `_TERMINOLOGY_PROPERTY_DEFAULTS` | 12 resource type to terminology property mappings | Query FHIR schema |
| `patterns/retrieve.py` | 74-79 | `_CODESYSTEM_PREFIXES` | Fallback codesystem URL prefixes | Load from config (now JSON) |

### C2. CQL/SQL Mappings (Acceptable)

| File | Line(s) | Dictionary | Status |
|------|---------|------------|--------|
| `expressions.py` | 112-167 | `BINARY_OPERATOR_MAP` | ACCEPTABLE - CQL spec, not FHIR |
| `expressions.py` | 169-176 | `UNARY_OPERATOR_MAP` | ACCEPTABLE - CQL spec, not FHIR |
| `operators.py` | 29-43 | `CQL_TYPE_TO_SQL` | ACCEPTABLE - CQL spec, not FHIR |
| `fhir_schema.py` | 26-45 | `FHIR_TYPE_TO_UDF` | ACCEPTABLE - UDF contract definition |
| `fhir_schema.py` | 48-67 | `FHIR_TYPE_TO_SQL` | ACCEPTABLE - SQL type mapping |
| `types.py` | 16 | `PRECEDENCE` | ACCEPTABLE - SQL semantics |

---

## Category D: String-based SQL Construction

*Definition: Building SQL logic using Python f-strings instead of AST node composition.*

### D1. SELECT/FROM/WHERE Construction (Critical)

| File | Line(s) | Pattern | Violation |
|------|---------|---------|-----------|
| `translator.py` | 434-438 | `f"WITH {', '.join(cte_parts)}"` and `f"SELECT * FROM {quoted_final}"` | Builds WITH clause via f-string |
| `translator.py` | 610-611 | `f"WITH\n  " + ",\n  ".join(cte_parts)` | Same pattern |
| `translator.py` | 659 | `f"WITH\n  {patients_cte}\nSELECT..."` | Same pattern |
| `translator.py` | 714 | `f"""SELECT p.patient_id, ({expr.to_sql()}) AS value FROM _patients p"""` | Builds SELECT via f-string |
| `translator.py` | 1440, 1448 | Same SELECT pattern | Duplicate |
| `translator.py` | 1612-1621 | Multi-line f-string SELECT construction | Complex query building |
| `translator.py` | 2875 | `f'CROSS JOIN LATERAL (SELECT * FROM "{cte_name}"...'` | JOIN construction |
| `translator.py` | 2933 | `f"\nLEFT JOIN {quoted_def} ON p.patient_id = {quoted_def}.patient_id"` | JOIN construction |
| `translator.py` | 2938 | `f"SELECT\n  {', '.join(select_parts)}\n{from_clause}\n{order_by}"` | Final SELECT assembly |
| `fluent_functions.py` | 1188, 1599 | `result.replace("FROM {resource}", f"FROM {resource_for_from}")` | Template manipulation |

### D2. FHIRPath Expression Construction (High)

| File | Line(s) | Pattern | Violation |
|------|---------|---------|-----------|
| `expressions.py` | 2722 | `f"code.coding.where(system='{system_url}' and code='{code_value}').exists()"` | Builds FHIRPath via f-string |
| `expressions.py` | 3629 | `f"{base_path}.where({where_clause}).{return_path}"` | FHIRPath construction |
| `terminology.py` | 273 | `f"{property_path}.coding.where(system='{codesystem_url}').exists()"` | Same pattern |
| `terminology.py` | 298 | `f"{property_path}.coding.where(system='...' and code='...').exists()"` | Same pattern |
| `patterns/retrieve.py` | 431 | `f"{coding_path}.where(system = '...' and code = '...').exists()"` | Same pattern |
| `fhirpath_builder.py` | 349 | `f"{base_path}.coding.where({or_conditions}).exists()"` | Same pattern |

### D3. INTERVAL Literals (Medium)

| File | Line(s) | Pattern | Violation |
|------|---------|---------|-----------|
| `expressions.py` | 5268 | `SQLRaw(raw_sql=f"INTERVAL '{quantity_value_int} {quantity_unit}'")` | Interval via f-string |
| `expressions.py` | 5395 | Same pattern | Duplicate |

---

## Category E: `list_filter` Lambda Patterns

*Definition: Generation of `list_filter(..., lambda)` strings instead of standard SQL WHERE clauses.*

| File | Line(s) | Context | Status |
|------|---------|---------|--------|
| `functions.py` | 285-293 | Comments and implementation for `list_filter` with lambda | Used for WHERE clause |
| `fluent_functions.py` | 573 | Comment about eliminating `list_filter` lambdas | Design goal |
| `fluent_functions.py` | 1191-1193 | `_wrap_list_filter_for_mixed_input` method | Template handling |
| `fluent_functions.py` | 1224-1276 | `_wrap_list_filter_for_mixed_input` implementation | Complex scalar/list handling |
| `fluent_functions.py` | 1307-1340 | Comments and code for `list_filter` patterns | Mixed input handling |
| `fluent_functions.py` | 1601-1606 | DeferredTemplateSubstitution handling | Template system |
| `expressions.py` | 1200, 4095, 4099, 4521, 4692-4697 | Detection and generation of `list_filter` | Expression handling |
| `ast_utils.py` | 689-711 | `ast_is_list_operation` checks for `list_filter` | AST utility |
| `patterns/aggregation.py` | 303 | Comment about `list_filter` for array expressions | Aggregation handling |

**Note:** `list_filter` is a valid DuckDB function. The violation is when it is generated via string templates instead of proper AST construction, or when it could be replaced with standard WHERE clauses in scalar contexts.

---

## Category F: Improper `SQLRaw` Usage

*Definition: Relying on `SQLRaw` to inject structured constructs instead of proper AST nodes.*

| File | Line(s) | Pattern | Issue |
|------|---------|---------|-------|
| `expressions.py` | 462 | `return SQLRaw(raw_sql=sql_expr_val)` | Wraps string instead of building AST |
| `expressions.py` | 948 | `SQLRaw(raw_sql=f"x -> {func_name}(x, '{path}')")` | Lambda expression as string |
| `expressions.py` | 1023-1043 | Multiple `isinstance(se, SQLRaw)` checks | Indicates SQLRaw is being used |
| `expressions.py` | 1245 | `source_sql = SQLRaw(raw_sql=sql_expr_val)` | Same as F1 |
| `expressions.py` | 5026 | `if isinstance(expr, SQLRaw):` | Type checking indicates usage |
| `expressions.py` | 5268, 5395 | `SQLRaw(raw_sql=f"INTERVAL ...")` | Should use SQLInterval |
| `patterns/joins.py` | 431, 438 | `return SQLRaw(raw_sql=str(...))` | Returns SQLRaw instead of AST |
| `types.py` | 309-328 | Defensive handling of `SQLRaw` with UNION ALL | Indicates legacy usage |
| `types.py` | 328 | `isinstance(arg, SQLRaw) and arg.raw_sql.startswith("DATE ")` | Date literal detection |
| `types.py` | 618-620 | `isinstance(self.low, SQLRaw)` checks | Interval bound handling |
| `translator.py` | 2182 | `isinstance(select.from_clause, SQLRaw)` | Legacy raw SQL detection |

---

## Category G: Pending Tasks (TODOs/FIXMEs/HACKs)

| File | Line(s) | Marker | Description |
|------|---------|--------|-------------|
| `expressions.py` | 182 | `TODO (Task C5)` | Replace with dynamic resolution from CQL valueset context |
| `expressions.py` | 3985 | `TODO` | Implement proper timezone offset extraction |
| `expressions.py` | 4308 | `TODO` | Implement proper multi-source query handling with CROSS JOIN |
| `expressions.py` | 5240, 5362 | `TODO` | Improve CQL parser to decompose temporal operators |
| `patterns/interval.py` | 696 | `TODO (REM-27, LOW)` | Implement collapse_intervals UDF in DuckDB extension |

---

## Category H: Dead Code

*Result: No dead code detected. Prior cleanup efforts appear successful.*

---

## File-by-File Summary

| File | A | B | C | D | E | F | G | Total |
|------|---|---|---|---|---|---|---|-------|
| `translator.py` | 35 | 0 | 0 | 12 | 0 | 1 | 0 | **48** |
| `fluent_functions.py` | 6 | 1 | 0 | 2 | 12 | 0 | 0 | **21** |
| `expressions.py` | 2 | 2 | 2 | 4 | 8 | 6 | 5 | **29** |
| `types.py` | 0 | 0 | 2 | 0 | 0 | 3 | 0 | **5** |
| `patterns/joins.py` | 0 | 0 | 0 | 0 | 0 | 2 | 0 | **2** |
| `patterns/retrieve.py` | 0 | 0 | 2 | 1 | 0 | 0 | 0 | **3** |
| `patterns/aggregation.py` | 0 | 0 | 0 | 0 | 1 | 0 | 0 | **1** |
| `patterns/interval.py` | 0 | 0 | 0 | 0 | 0 | 0 | 1 | **1** |
| `terminology.py` | 0 | 0 | 0 | 3 | 0 | 0 | 0 | **3** |
| `property_scanner.py` | 0 | 1 | 0 | 0 | 0 | 0 | 0 | **1** |
| `ast_utils.py` | 0 | 1 | 0 | 0 | 1 | 0 | 0 | **2** |
| `fhirpath_builder.py` | 0 | 0 | 0 | 1 | 0 | 0 | 0 | **1** |
| `functions.py` | 0 | 0 | 0 | 0 | 3 | 0 | 0 | **3** |
| `operators.py` | 0 | 0 | 1 | 0 | 0 | 0 | 0 | **1** |
| `fhir_schema.py` | 0 | 0 | 2 | 0 | 0 | 0 | 0 | **2** |
| **Totals** | **43** | **5** | **9** | **23** | **25** | **12** | **6** | **123** |

---

## Recommendations

### Priority 1: `translator.py` Refactoring (48 violations)
The main translator has the highest concentration of violations:
- 35 unauthorized `.to_sql()` calls in CTE building methods
- 12 f-string SQL construction patterns

**Action:** Refactor `_build_definition_cte_with_patient_id`, `_build_cte_from_ast`, and related methods to return AST nodes instead of strings.

### Priority 2: `expressions.py` Template Migration (29 violations)
The expression translator uses string templates and `list_filter` patterns:
- 5 TODO markers indicating known technical debt
- 8 `list_filter` related patterns
- 4 f-string FHIRPath constructions

**Action:** Complete Task C5 (dynamic component code resolution) and migrate FHIRPath construction to `fhirpath_builder.py`.

### Priority 3: `fluent_functions.py` AST Conversion (21 violations)
The fluent function system still uses string templates:
- 6 `.to_sql()` calls for template substitution
- 12 `list_filter` handling patterns

**Action:** Convert `DeferredTemplateSubstitution` to operate on AST nodes instead of strings.

---

## Comparison with PLAN-ARCHITECTURAL-REMEDIATION.md

| Original Estimate | Phase 2 Finding | Assessment |
|-------------------|-----------------|------------|
| 21 regex sites | 5 remaining | 76% reduction |
| ~12 `.to_sql()` inspection | 43 unauthorized | More thorough scan |
| 22 hardcoded dicts | 9 FHIR-related | 59% reduction |
| Not cataloged | 23 f-string SQL | New inventory |
| Not cataloged | 25 `list_filter` patterns | New inventory |
| Not cataloged | 12 SQLRaw issues | New inventory |
| Not cataloged | 6 TODOs | New inventory |

---

## Appendix: Scan Methodology

1. **Pattern Searches:** Used `grep` for `.to_sql()`, `re.search/match/sub`, `TODO/FIXME/HACK`, `list_filter`, `SQLRaw`
2. **File Reading:** Read all 32 Python files in `cql-py/src/cql_py/translator/`
3. **Classification:** Each finding categorized by violation type and severity
4. **Verification:** Cross-referenced with `PLAN-ARCHITECTURAL-REMEDIATION.md` design principles

---

*End of Phase 2 Audit Inventory*
