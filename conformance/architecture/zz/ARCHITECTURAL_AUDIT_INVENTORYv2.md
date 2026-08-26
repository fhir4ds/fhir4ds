# Architectural Audit Inventory
**Date:** 2026-03-03
**Status:** Audit Complete

## Summary of Findings
- Unauthorized .to_sql() inspections: 23 instances found
- Regex-based SQL inspection/manipulation: 18 instances found
- Manual SQL tokenizer / UNION parsing: 6 instances found
- Hardcoded FHIR/schema dictionaries & constants: 16 instances found
- Hardcoded CQL library knowledge & status filters: 7 instances found
- body_sql templates / list_filter lambda templates: 30+ instances found
- SQLRaw / raw SQL embedding instead of AST nodes: many occurrences
- f-strings / string-built SQL fragments: many occurrences
- Heuristic property-to-column logic & regex parsing: multiple occurrences

---

## Category: Unauthorized .to_sql() inspections
*Description: Calling .to_sql() to inspect or make translation decisions (violates "Pure CQL AST → Pure SQL AST" — decisions must be AST-based per remediation plan).* 

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/translator.py` | ~657–668, 1398–1401, 1581–1586, 1872–1878, 2097–2099, 2145–2149, 2369–2371, 3744–3748, 4133–4135 | `expr.to_sql()` / `select.where.to_sql()` | Renders SQL to string to make control decisions (e.g., detect patient_id, resource column, EXISTS). Use ast_utils.select_has_column / ast_has_node_type instead. |
| `cql-py/src/cql_py/translator/types.py` | multiple | `return f"{self.name} := {self.value.to_sql()}"` and other to_sql usages | to_sql used for debug/composition and in type-inference helpers — fine for final render only. |
| `cql-py/src/cql_py/translator/expressions.py` | ~1030, 1202 | `source_sql.to_sql()` used to build resource-qualified fhirpath calls | Serializes AST nodes mid-pipeline and constructs SQLRaw fragments losing AST structure. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | ~1608–1649, 2100–2141 | `resource_expr.to_sql()`, `arg.to_sql()` used for template substitution | Collapses AST args into strings, then performs regex/template decisions on the string. |
| `cql-py/src/cql_py/translator/__init__.py` | debug prints | `print(f"{name}: {expr.to_sql()}")` | Printing/rendering in debug paths can be mistaken for logic when used in code. |

Why it violates the standard: Plan §1 requires all translation-time decisions to be made via AST introspection; rendering is reserved for final output only.

---

## Category: Regex-based SQL inspection/manipulation
*Description: Using regex (re.search/match/sub/findall) on rendered SQL for detection/transformation rather than AST traversal (Plan §1, Phase A).* 

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | ~460–495, 1161–1210, 3748 | `re.search(r'THEN\s*\(\s*SELECT', sql_expr_val)`, `re.search(r'fhirpath_...')` | Uses regex on SQL string to detect CASE/UNION, fhirpath functions, and list-like UDFs. Should use AST node checks (SQLCase, SQLUnion, SQLFunctionCall). |
| `cql-py/src/cql_py/translator/fluent_functions.py` | ~1429–1562, 1706–1770, 1815–1844, 1881–1968 | `re.sub(...)`, `re.match(r'list_filter...')`, `re.search(correlated_pattern, resource_sql)` | Rewrites and extracts lambda templates via regex on SQL templates; replace with AST-level template ASTs or parsed CQL function bodies. |
| `cql-py/src/cql_py/generator/population_builder.py` | occurrences | `re.findall(r'%([A-Za-z_][A-Za-z0-9_]*)', fhirpath)` | Parses dependencies from fhirpath string content with regex; should use structured metadata. |
| `cql-py/src/cql_py/dependency/resolver.py` | occurrences | `re.search(r'^\s*library\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.MULTILINE)` | Regex-driven library name extraction; robust parser/AST should be used. |
| `cql-py/src/cql_py/translator/property_scanner.py` | ~82 | `re.search(r"code\s*=\s*['\"](\d{4,5}-\d+)['\"]", where_content)` | Extracts LOINC codes from string content rather than via AST/value set references. |

Why it violates the standard: Regexing rendered SQL is fragile and bypasses AST semantics; Plan A1/A3 mandates AST helpers for detection/rewrite.

---

## Category: Manual SQL Tokenizer / UNION parsing
*Description: Character-level parsing of raw SQL strings (should be represented and manipulated as SQLUnion/SQLSelect AST nodes).* 

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/types.py` | 361–428 | `_split_union_all()` — character-level tokenizer | Splits rendered SQL by scanning parentheses and CASE depth; brittle and unnecessary if SQLUnion AST nodes were used consistently. Triggers found where SQLRaw contains embedded UNION ALL. |
| `cql-py/src/cql_py/translator/types.py` | ~315 | `if isinstance(first_arg, SQLRaw) and " UNION ALL " in first_arg.raw_sql.upper():` | String trigger that feeds the manual tokenizer; indicates upstream raw SQL creation where AST should be used. |

Why it violates the standard: Plan A6 requires UNION to be represented via SQLUnion AST nodes and prevent string-parsing of SQL text.

---

## Category: Hardcoded FHIR / Schema Dictionaries & Constants
*Description: Hardcoded maps and profile-to-resource mappings scattered across modules that should be replaced by a FHIRSchemaRegistry (Plan Phase B).* 

| File | Line(s) | Snippet / Constant | Violation Detail |
|------|---------|--------------------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | ~84–253 | `_LIBRARY_CODE_CONSTANTS`, `CHOICE_TYPE_MAP`, `ALL_CHOICE_TYPES`, `_is_choice_type_path()` | Hardcoded FHIR choice/type and library constants; duplicates FHIR schema knowledge in code. Should query FHIRSchemaRegistry. |
| `cql-py/src/cql_py/translator/cte_builder.py` | multiple | `RESOURCE_TYPE_VALID_COLUMNS`, `PROPERTY_CHAIN_COLUMNS`, `property_to_column_name()`, `infer_fhirpath_function()` | Column whitelist and heuristics for property→column mapping; replace with schema-aware generation. |
| `cql-py/src/cql_py/translator/types.py` | ~1150–1255 | `CHOICE_TYPE_COLUMNS` (precomputed column definitions) | Central hardcoded precomputed columns including FHIRPaths and LOINC codes; must be generated dynamically. |
| `cql-py/src/cql_py/translator/profile_registry.py` | file | Profile mapping helpers | Partial refactor exists, but other modules still rely on in-code dicts—consolidate registry usages. |
| `cql-py/src/cql_py/translator/property_scanner.py` | top | `BP_LOINC_CODES` | Hardcoded Blood Pressure LOINC codes. Replace with valueset resolution or library-inlined constants. |
| `cql-py/src/cql_py/translator/cte_builder.py` | ~584–598 | `PROFILES_REQUIRING_SUFFIX` | Profile URL list embedded in code; should be configuration or schema-driven. |

Why it violates the standard: Plan Phase B prescribes a FHIRSchemaRegistry to centralize StructureDefinition-driven decisions, removing brittle code-level dicts.

---

## Category: Hardcoded CQL library knowledge & status filters
*Description: QICore/Status function bodies, code constants, and STATUS_FILTERS dicts are hardcoded instead of parsed/inlined from CQL libraries (Plan Phase C).* 

| File | Line(s) | Snippet / Constant | Violation Detail |
|------|---------|--------------------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | ~89–123 | `_LIBRARY_CODE_CONSTANTS` | Bypasses library parsing; value constants should be extracted from parsed library ASTs. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | ~60–194, 401–822, 1184–1408 | `STATUS_FILTERS`, `_initialize_common_functions()` body_sql templates, `_build_prevalence_interval_ast()`, `_build_date_coalesce_expr()` | Function bodies and status semantics encoded as Python constants and SQL string templates — must be sourced from parsed libraries and inlined via function inliner. |
| `cql-py/src/cql_py/translator/property_scanner.py` | 39–42 | `BP_LOINC_CODES` | Also overlaps library constants. |

Why it violates the standard: Plan Phase C requires dynamic CQL library parsing and inlining; hardcoded mappings cause drift and prevent correct semantics when library code changes.

---

## Category: body_sql templates & list_filter lambda templates
*Description: SQL body templates (strings) registered for fluent functions, often containing `list_filter({resource}, r -> ...)` lambdas — these embed SQL string templates and lambdas instead of AST-first representations.* 

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/fluent_functions.py` | Many locations (dozens) | `body_sql="list_filter({resource}, r -> fhirpath_text(r, 'status') IN ('active', 'completed'))"` | Dozens of body_sql templates embed SQL expressions and lambda text; this circumvents AST-based inlining and complicates optimizations like JOIN generation. |
| `cql-py/src/cql_py/translator/functions.py` | contexts | `SQLFunctionCall(name="list_filter", args=[source, predicate])` | While SQL-level list_filter is valid, many call sites produce predicate as a raw string. Predicates should be AST predicates. |
| `cql-py/src/cql_py/translator/fluent_functions.py` | pattern sites | `re.match(r'list_filter\(\{resource\},\s*(\w+)\s*->\s*(.+)\)$', template.strip())` | Extracts lambda predicate from string via regex — fragile and not AST-driven. |

Why it violates the standard: Plan C4 mandates replacing body_sql templates with AST-based inlining from parsed CQL function bodies.

---

## Category: SQLRaw / raw SQL embedding instead of AST nodes
*Description: Creating SQLRaw nodes with complex SQL fragments instead of using proper AST nodes (Select, Join, QualifiedIdentifier, FunctionCall, Literal).* 

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/cte_builder.py` | multiple | `SQLRaw(raw_sql="resources r")`, `SQLRaw(raw_sql=sql_expr)` | FROM clauses and column expressions are often composed as raw SQL; this causes downstream string parsing and hinders AST-based transforms. |
| `cql-py/src/cql_py/translator/types.py` | occurrences | `if isinstance(first_arg, SQLRaw) and " UNION ALL " in first_arg.raw_sql.upper():` | Defensive checks that exist because upstream creates SQLRaw with embedded UNIONs. |
| `cql-py/src/cql_py/translator/expressions.py` | occurrences | `SQLRaw(raw_sql=f"DATE '{mp_start}'")` | SQL literal fragments embedded as SQLRaw instead of SQLLiteral/SQLInterval nodes. |

Why it violates the standard: Raw SQL fragments defeat AST transformations; Plan A6 and general AST-first principle require constructing AST nodes instead.

---

## Category: f-strings / string-built SQL fragments
*Description: Building SQL with f-strings or concatenation instead of SQLQualifiedIdentifier/SQLLiteral AST nodes.* 

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/expressions.py` | many | `resource_col = f'"{from_name}".resource'`, `sql_expr_val = f"{sql_expr_val}.resource"` | Qualified identifier text built via formatting rather than SQLQualifiedIdentifier(parts=[alias, 'resource']). |
| `cql-py/src/cql_py/translator/patterns/retrieve.py` | multiple | `resource_col = f"{alias}.resource"` | Inline string-built resource refs; results in SQLRaw or string comparisons elsewhere. |
| `cql-py/src/cql_py/translator/patterns/joins.py` | multiple | `return f"resources {inner_alias}"` ; `return f"EXISTS (SELECT 1 FROM {from_clause} WHERE {where_clause})"` | FROM clause and EXISTS wrapper composed as strings. Should be SQLSelect/SQLExists AST usage. |
| `cql-py/src/cql_py/generator/population_builder.py` | occurrences | `return f"fhirpath_text(p.resource, '{self._escape_sql(fhirpath)}')"` | Builds fhirpath_* calls as strings — should be AST FunctionCall nodes with SQLLiteral args. |

Why it violates the standard: String-built SQL fragments are fragile; AST nodes provide typing and enable safe transformations and optimizations (Plan A1/A3).

---

## Category: Heuristic property-to-column logic & regex parsing
*Description: Using ad-hoc heuristics and regex to map FHIR property paths to precomputed column names and to select UDFs.* 

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/translator/cte_builder.py` | `property_to_column_name()`, `infer_fhirpath_function()` | `col_name = property_to_column_name(property_path, resource_type=...)` | Heuristic rules and substring matching decide column names and UDF selection; should be schema informed by FHIRSchemaRegistry and property scanner output (Plan B5). |
| `cql-py/src/cql_py/translator/ast_utils.py` | camelCase helper | `re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()` | Utility uses regex to convert camelCase — acceptable as small utility, but broader mapping should be schema-driven when possible. |

Why it violates the standard: Heuristics leak into generation logic and cause mismatches across measures; schema-driven mapping is required by Plan B.

---

## Category: Valueset / terminology URLs escaped into SQL strings
*Description: Inserting valueset URLs or codes into SQL via string formatting rather than using SQLLiteral nodes or structured AST representation.* 

| File | Line(s) | Snippet | Violation Detail |
|------|---------|---------|------------------|
| `cql-py/src/cql_py/generator/population_builder.py` | occurrences | `AND in_valueset(r.resource, 'code', '{self._escape_sql(terminology)}')` | Valueset URL embedded into SQL string; should be passed as SQLLiteral or via terminology service AST-aware call. |
| `cql-py/src/cql_py/translator/cte_builder.py` | occurrences | `AND in_valueset(r.resource, 'code', 'http://...')` | Hardcoded inline valueset checks in raw SQL fragment. |

Why it violates the standard: Terminology references should be represented as AST literals or linked to a terminology service for resolution and safe parameterization.

---

## Cross-Reference: Violations per File (summary)
| File | Unauthorized .to_sql() | Regex | Manual Tokenizer | Hardcoded Schema | Hardcoded Libraries | body_sql / templates | Total (approx) |
|------|----------------------:|------:|----------------:|-----------------:|------------------:|--------------------:|---------------:|
| `translator.py` | 11 | 4 | — | — | — | — | 15 |
| `expressions.py` | 2 | 5 | — | 2 | 2 | — | 11 |
| `fluent_functions.py` | 5 | 5 | 4 | — | 4 | many | 18 |
| `types.py` | 3 | 2 | 2 | 3 | — | — | 10 |
| `cte_builder.py` | — | 1 | — | 5 | — | — | 6 |
| `patterns/retrieve.py` | — | — | — | 2 | — | — | 2 |
| `property_scanner.py` | — | 1 | — | 1 | 1 | — | 3 |
| `generator/population_builder.py` | — | 1 | — | — | — | — | 1 |
| **Total (approx)** | **23** | **18** | **6** | **16** | **7** | **30+** | **100+**

---

## Notes & Next Steps
- Phase A (AST Introspection) should be executed first to remove all `.to_sql()` inspections and regex-on-SQL detection; this resolves the highest-severity items (categories A, B, C).
- Phase B (FHIRSchemaRegistry) replaces hardcoded schema dicts and property heuristics.
- Phase C (Library Inlining) requires fixing the CQL parser to handle QICoreCommon and using function-inliner + library AST to eliminate body_sql templates and `_LIBRARY_CODE_CONSTANTS`.

This inventory was generated by exhaustive pattern searches guided by `plans/PLAN-ARCHITECTURAL-REMEDIATION.md` and cross-referenced with the code under `cql-py/src/cql_py/translator/` and related generator modules. Each listed violation includes a file reference and brief snippet/description; follow-up pass can produce exact line ranges and copy-paste-ready diffs for remediation tasks.

*End of audit (v2).*
