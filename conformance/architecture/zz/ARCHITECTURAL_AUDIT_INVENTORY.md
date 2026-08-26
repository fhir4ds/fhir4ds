# Architectural Audit Inventory
**Date:** 2026-03-02
**Status:** Audit Complete
**Scope:** `cql-py/src/cql_py/translator/` — 29 Python files scanned
**Reference:** `plans/PLAN-ARCHITECTURAL-REMEDIATION.md`

## Summary of Findings

| Anti-Pattern Category | Instances |
|---|---|
| A. `.to_sql()` for Inspection/Decision-Making | 23 instances |
| B. Regex on SQL/FHIRPath Strings | 18 instances |
| C. Manual SQL Tokenizer | 6 instances |
| D. Hardcoded FHIR Schema Dicts | 16 instances |
| E. Hardcoded CQL Library Knowledge | 7 instances |
| F. Hardcoded QICore/Profile Mappings | 4 instances |
| **Total** | **74 instances** |

### Remediation Files (Not Flagged)
The following new files exist as part of ongoing remediation and contain no violations:
- `ast_utils.py` — AST inspection utilities (Phase A)
- `fhir_schema.py` — FHIRSchemaRegistry (Phase B)
- `profile_registry.py` — JSON-backed profile registry (Phase B)
- `status_filter_extractor.py` — Dynamic status filter extraction (Phase C)

### Clean Files (No Violations Found)
- `column_registry.py`, `context.py`, `warnings.py`, `library_resolver.py`
- `terminology.py`, `placeholder.py`, `retrieve_optimizer.py`, `function_inliner.py`
- `patterns/interval.py`, `patterns/quantity.py`, `patterns/__init__.py`, `__init__.py`
- `queries.py`

---

## Category A: `.to_sql()` Called for Inspection/Decision-Making
*The translator must never inspect or manipulate SQL text mid-pipeline. All decisions must be made using AST metadata. The **only** place `.to_sql()` should be called is the Phase 3 final assembly step. (§1, Principle 1)*

| # | File | Line(s) | Snippet | Violation Detail |
|---|------|---------|---------|------------------|
| A1 | `translator.py` | 657–661 | `sql = wrapped_ast.to_sql(); if self._has_unresolved_refs(sql):` | Renders AST to string to feed regex validator `_has_unresolved_refs`. Decision-making on rendered SQL. |
| A2 | `translator.py` | 667–668 | `sql_str = expr.to_sql(); if "patient_id" in sql_str.lower():` | Renders to string to check `"patient_id"` presence by substring search. |
| A3 | `translator.py` | 1398–1401 | `sql = expr.to_sql(); if "patient_id" in sql.lower():` | Same pattern: renders to check `"patient_id"` in `_build_definition_cte_with_patient_id`. |
| A4 | `translator.py` | 1581–1586 | `sql = select.to_sql(); if "patient_id" not in sql.lower():` | Renders SELECT, inspects for `"patient_id"` to decide wrapping in `_build_cte_from_ast`. |
| A5 | `translator.py` | 1872–1878 | `col_str = str(expr.to_sql()).lower(); if 'resource' in col_str:` | `_select_has_resource` renders each column to substring-search for `'resource'`. |
| A6 | `translator.py` | 2097–2099 | `where_str = select.where.to_sql().upper(); if "EXISTS" in where_str:` | `_is_ast_boolean_expression` renders WHERE clause to check for `"EXISTS"` substring. Should use `isinstance(_, SQLExists)`. |
| A7 | `translator.py` | 2145–2149 | `sql = select.to_sql(); if "resources r" not in sql.lower(): sql = sql.replace(...)` | Renders then patches alias via `str.replace` — string mutation of rendered SQL. |
| A8 | `translator.py` | 2171–2173 | `sql = select.to_sql(); if "patient_id" in sql.lower():` | `_wrap_ast_boolean_with_patient_id` renders to check `"patient_id"`. |
| A9 | `translator.py` | 2369–2371 | `where_sql = inner_select.where.to_sql(); if "patient_id" in where_sql and outer_alias in where_sql:` | `_correlate_exists_ast` renders WHERE to check correlation — inside a method documented as not calling `.to_sql()`. |
| A10 | `translator.py` | 3744–3748 | `sql_text = expr.to_sql(); if f'"{other_name}"' in sql_text:` | `_sort_included_definitions` renders all defs to build dependency graph by substring matching. |
| A11 | `translator.py` | 328 | `self._context.add_definition(name, ast.to_sql())` | Stores rendered SQL string in context instead of AST; downstream consumers inspect strings. |
| A12 | `expressions.py` | 1030 | `resource_col = f"{source_sql.to_sql()}.resource"` | Renders AST node to construct raw SQL string for fhirpath call. Creates opaque `SQLRaw`. |
| A13 | `expressions.py` | 1202 | `resource_sql = existing_resource.to_sql(); return SQLRaw(raw_sql=f"{func_name}({resource_sql}, ...")` | Renders sub-AST node to build `SQLRaw` for chained fhirpath — loses all structure. |
| A14 | `fluent_functions.py` | 1608, 1613 | `resource_sql = resource_expr.to_sql(); if '.' not in resource_sql and '(' not in resource_sql:` | `_substitute_template` renders expr then char-tests to decide `.resource` qualification. |
| A15 | `fluent_functions.py` | 1649 | `param_map[param_name] = arg.to_sql()` | Args collapsed to strings mid-pipeline for string template substitution. |
| A16 | `fluent_functions.py` | 2100 | `return SQLFunctionCall(name="COALESCE", args=coalesce_args).to_sql()` | Fresh AST node immediately `.to_sql()`'d and discarded inside `DeferredTemplateSubstitution`. |
| A17 | `fluent_functions.py` | 2115, 2121 | `resource_sql = self._resource_expr.to_sql(); if '.' not in resource_sql:` | Deferred path duplicate of A14 — same `.resource` qualification decision on serialized string. |
| A18 | `fluent_functions.py` | 2141 | `param_map[param_name] = arg.to_sql()` | Deferred path duplicate of A15 — mid-pipeline arg collapse. |
| A19 | `types.py` | 769–770 | `table_sql = self.table.to_sql(); if not table_sql.startswith('('):` | `SQLJoin.to_sql()` inspects rendered string with `startswith('(')` after `isinstance` already done. |
| A20 | `types.py` | 843–846 | `from_sql = self.from_clause.to_sql(); if not from_sql.startswith('('):` | `SQLSelect.to_sql()` FROM clause — same redundant `startswith('(')` check. |
| A21 | `types.py` | 1577–1584 | `sql = op.to_sql(); stripped = sql.strip(); if stripped.startswith('(') and stripped.endswith(')'):` | `SQLUnion.to_sql()` parses rendered string char-by-char to detect bare identifiers vs SELECT. Most egregious inspection. |
| A22 | `aggregation.py` | 302–305 | `source_sql_str = source_sql.to_sql(); if "jsonConcat" in source_sql_str.lower():` | `translate_exists()` renders AST to string for substring matching. |
| A23 | `joins.py` | 569 | `return sql_expr.to_sql()` | `_translate_general_expression()` emits string mid-translation instead of returning AST. |

---

## Category B: Regex on SQL/FHIRPath Strings
*All decisions must be made using AST metadata, not by parsing rendered SQL with regular expressions. (§1, Principle 1)*

| # | File | Line(s) | Snippet | Violation Detail |
|---|------|---------|---------|------------------|
| B1 | `translator.py` | 689–692 | `re.search(r'fhirpath_text\([A-Z],', sql)` | `_has_unresolved_refs` applies regex to rendered SQL to detect single-letter aliases. |
| B2 | `translator.py` | 2797–2825 | `re.findall(alias_pattern, sql)` + `re.findall(cte_ref_pattern, sql)` | `_add_lateral_joins_for_aliases` uses two regexes on SQL string for alias and CTE ref discovery. |
| B3 | `translator.py` | 4133–4143 | `re.search(r"resourceType\s*=\s*'(\w+)'", where_str)` + `re.search(r"in_valueset\s*\(...")` | `_normalize_retrieve_pattern` extracts resource type and valueset URL from rendered WHERE via regex. |
| B4 | `expressions.py` | 462–469 | `re.search(r'THEN\s*\(\s*SELECT', sql_expr_val)` | Detects CASE+UNION pattern in serialized SQL string by regex. |
| B5 | `expressions.py` | 460, 471–473 | `'CASE WHEN' in sql_expr_val.upper()` + `any(op in sql_expr_val for op ...)` | String-contains inspection of serialized SQL for `list_filter`, `> 0`, etc. (non-regex but same anti-pattern). |
| B6 | `expressions.py` | 1161–1174 | `any(op in sql_expr_val for op in ['list_filter', 'jsonConcat', ...])` | Same substring-based expression classification in `_translate_property`. |
| B7 | `expressions.py` | 5167–5177 | `re.match(r"(starts\|ends)\s+(\d+...)...", operator)` | Re-parses CQL temporal operator string with regex in `_translate_complex_interval_temporal`. |
| B8 | `expressions.py` | 5284–5291 | `re.match(r"(starts\|ends)\s+(\d+...)...", operator)` | Duplicate of B7 in `_translate_complex_interval_temporal_with_interval`. |
| B9 | `fluent_functions.py` | 1429, 1444–1445 | `re.search(unsafe_quote_pattern, template)` | `_validate_template_substitution_safety` applies regex to SQL template to detect fhirpath quoting issues. |
| B10 | `fluent_functions.py` | 1537–1549 | `re.sub(pattern, replacement, template)` in loop | `_optimize_template_with_precomputed_columns` rewrites fhirpath UDF calls → column refs via `re.sub`. Most severe regex violation. |
| B11 | `fluent_functions.py` | 1764, 1773, 1778 | `re.match(r'list_filter\(...\)', template)` + `re.sub(r'\b' + ..., resource_sql, predicate)` | `_wrap_list_filter_for_mixed_input` parses `list_filter` lambda structure and substitutes vars via regex. |
| B12 | `fluent_functions.py` | 1815, 1844 | `re.search(r'\bCASE\b', resource_upper)` | `_wrap_boolean_for_list` detects CASE/scalar expression type via regex on serialized SQL. |
| B13 | `fluent_functions.py` | 1881, 1916–1933 | `re.match(simple_identifier_pattern, resource_sql)` + `re.search(correlated_pattern, resource_sql)` | `_wrap_for_table_source` classifies expression kind (identifier/subquery/correlated ref) via regex. |
| B14 | `types.py` | 1389–1390 | `re.sub(r'(?<!^)(?=[A-Z])', '_', base_prop).lower()` | camelCase→snake_case via regex in `generate_column_definitions_from_schema` (choice branch). |
| B15 | `types.py` | 1415–1416 | `re.sub(r'(?<!^)(?=[A-Z])', '_', prop).lower()` | Duplicate camelCase→snake_case via regex (regular branch). |
| B16 | `cte_builder.py` | 170, 175 | `re.sub(r'(?<!^)(?=[A-Z])', '_', base).lower()` | `property_to_column_name` camelCase→snake_case via regex. |
| B17 | `property_scanner.py` | 82 | `re.search(r"code\s*=\s*['\"](\d{4,5}-\d)['\"]", property_path)` | Extracts LOINC codes from FHIRPath expression strings via regex instead of AST. |
| B18 | `translator.py` | (5+ sites) | Various `re.search`/`re.sub` | Additional minor regex sites referenced in remediation plan. |

---

## Category C: Manual SQL Tokenizer
*Character-by-character SQL parsing that should operate on AST nodes instead. (§2.1C)*

| # | File | Line(s) | Snippet | Violation Detail |
|---|------|---------|---------|------------------|
| C1 | `types.py` | 366–454 | `_split_union_all()` — 90 lines | Character-by-character SQL tokenizer tracking paren depth and CASE/END nesting to split `UNION ALL`. Should operate on `SQLUnion` AST nodes. |
| C2 | `types.py` | 315 | `if isinstance(first_arg, SQLRaw) and " UNION ALL " in first_arg.raw_sql.upper():` | String-scan trigger that invokes the manual tokenizer. |
| C3 | `fluent_functions.py` | 1613, 1626–1629 | `if '.' not in resource_sql and '(' not in resource_sql: ... if f"{fhir_func}{param_placeholder}" in template:` | Multi-pass string scan to classify expression shape and detect fhirpath calls. |
| C4 | `fluent_functions.py` | 1706, 1712–1719 | `elif "list_filter({resource}" in template: ...` + `any(op in resource_sql for op in ['jsonConcat', ...])` | Template-type dispatch by scanning body_sql for literal substrings. |
| C5 | `fluent_functions.py` | 1767–1769, 2169–2171 | `any(op in resource_sql for op in ['jsonConcat', 'list_filter', 'list_apply', 'list_aggr'])` | List-type detection via string scan, duplicated in 3 locations. |
| C6 | `fluent_functions.py` | 1923–1924 | `stripped.startswith('(') and stripped.endswith(')')` | Parenthesis-boundary check on raw SQL string instead of `isinstance(_, SQLSubquery)`. |

---

## Category D: Hardcoded FHIR Schema Dicts
*FHIR type knowledge should come from StructureDefinition metadata, not hardcoded dicts. (§2, Principle 2; §3, Principle 3)*

| # | File | Line(s) | Dict/Constant | Entries | Violation Detail |
|---|------|---------|---------------|---------|------------------|
| D1 | `expressions.py` | 1325–1333 | `common_choice_elements` set in `_is_choice_type_path` | ~35 elements | Hardcoded FHIR choice element names. Fallback when `FHIRSchemaRegistry` unavailable. |
| D2 | `expressions.py` | 1360–1366 | Hardcoded fallback list in `_get_choice_types_for_resource` | 16 types | All possible choice type suffixes — applied regardless of resource/path. |
| D3 | `types.py` | 1153–1255 | `CHOICE_TYPE_COLUMNS` | 16 columns | Central precomputed column definitions: FHIRPaths, SQL types, profiles, LOINC codes all hardcoded. |
| D4 | `types.py` | 1261–1273 | `DEFAULT_SORT_COLUMNS` | 11 resources | Raw SQL ORDER BY strings per resource type. Not AST nodes. |
| D5 | `types.py` | 964 | `_CHOICE_TYPE_COLUMN_NAMES` on `SQLRetrieveCTE` | 3 prefixes | Hardcoded set `{"value", "onset", "effective"}` for column classification. |
| D6 | `cte_builder.py` | 42–91 | `RESOURCE_TYPE_VALID_COLUMNS` | 14 resources | Whitelist of valid precomputed columns per resource type. |
| D7 | `cte_builder.py` | 98–110 | `PROPERTY_CHAIN_COLUMNS` | 4 chains | Deep FHIRPath → raw SQL expression mappings. |
| D8 | `cte_builder.py` | 135–154 | `property_to_column_name()` inline dict | 18 mappings | FHIRPath property → SQL column name. |
| D9 | `cte_builder.py` | 584–598 | `PROFILES_REQUIRING_SUFFIX` | 8 URLs | US Core profile URLs requiring CTE-name suffix. |
| D10 | `operators.py` | 29–43 | `CQL_TYPE_TO_SQL` | 13 types | CQL → SQL type cast mapping. (Note: remediation plan considers this acceptable — CQL spec, not FHIR schema.) |
| D11 | `temporal.py` | 44–54 | `PRECISION_LEVELS` | 9 levels | CQL temporal precision orderings. (Note: remediation plan considers this acceptable — ISO 8601 semantics.) |
| D12 | `temporal.py` | 57–67 | `PRECISION_TRUNCATE_FUNCTIONS` | 9 functions | DuckDB truncation templates. (Note: remediation plan considers this acceptable — SQL semantics.) |
| D13 | `property_scanner.py` | 39–42 | `BP_LOINC_CODES` | 2 codes | Blood pressure LOINC codes (duplicated from `COMPONENT_CODE_TO_COLUMN`). |
| D14 | `retrieve.py` | 43–58 | `DEFAULT_TERMINOLOGY_PROPERTIES` | 14 resources | Default code path per resource type for valueset testing. |
| D15 | `cte_builder.py` | ~185–200 | `infer_fhirpath_function()` inline heuristics | 4 rules | Substring matching on property name to guess UDF type. |
| D16 | `retrieve.py` | 518–529, 606–615 | Inline `codesystem_prefixes` dict (×2) | 9 entries × 2 | Hardcoded codesystem name → URL mappings, duplicated in two methods. |

---

## Category E: Hardcoded CQL Library Knowledge
*External libraries (QICoreCommon, Status, FHIRHelpers) should be parsed and inlined dynamically, not hardcoded. (§2, Principle 2)*

| # | File | Line(s) | Dict/Constant | Entries | Violation Detail |
|---|------|---------|---------------|---------|------------------|
| E1 | `expressions.py` | 89–123 | `_LIBRARY_CODE_CONSTANTS` | ~24 values | QICoreCommon constants (ambulatory, emergency, LOINC codes, etc.) bypass library parsing. |
| E2 | `expressions.py` | 215–218 | `COMPONENT_CODE_TO_COLUMN` | 2 LOINC codes | BP component LOINC → column mapping — CMS165-specific. |
| E3 | `fluent_functions.py` | 60–194 | `STATUS_FILTERS` | 22 rules | Status/intent filtering logic from Status.cql and QICoreCommon.cql as a Python dict. |
| E4 | `fluent_functions.py` | 401–822 | `_initialize_common_functions()` | ~30 body_sql templates | 421 lines of hardcoded SQL string templates encoding QICoreCommon/Status/FHIRHelpers function bodies. |
| E5 | `fluent_functions.py` | 1184–1276 | `_build_prevalence_interval_ast()` | 3 paths | Hand-coded QICoreCommon.prevalenceInterval() as Python AST construction (onset, abatement, recordedDate). |
| E6 | `fluent_functions.py` | 1366–1408 | `_build_date_coalesce_expr()` | 2 paths | Hardcodes effectiveDateTime → COALESCE(effectiveDateTime, effectivePeriod.start) choice resolution. |
| E7 | `property_scanner.py` | 39–42 | `BP_LOINC_CODES` | 2 codes | Blood pressure LOINC codes (also counted in D13 — overlaps both categories). |

---

## Category F: Hardcoded QICore/Profile Mappings
*Profiles are inferred from CQL usage patterns, not from a hardcoded registry. (§6.1, cql-translator-technical-spec.md)*

| # | File | Line(s) | Dict/Constant | Entries | Violation Detail |
|---|------|---------|---------------|---------|------------------|
| F1 | `retrieve.py` | 63–80 | `QICORE_PROFILE_PATTERNS` | 16 patterns | QICore base type → generic profile URL. Still used as fallback after `ProfileRegistry`. |
| F2 | `retrieve.py` | 88–183 | `QICORE_TO_FHIR_TYPE` | 20+ mappings | QICore profile name → (FHIR type, URL). Still used as fallback at line 312. |
| F3 | `retrieve.py` | 187–201 | `USCORE_PROFILE_TO_FHIR_TYPE` | 8+ mappings | US Core profile URL → FHIR type. Still used as fallback. |
| F4 | `retrieve.py` | 43–58 | `DEFAULT_TERMINOLOGY_PROPERTIES` | 14 resources | Default code path per resource type (also counted in D14 — overlaps both categories). |

---

## Cross-Reference: Violations per File

| File | Cat A | Cat B | Cat C | Cat D | Cat E | Cat F | Total |
|------|-------|-------|-------|-------|-------|-------|-------|
| `translator.py` | 11 | 4 | — | — | — | — | **15** |
| `expressions.py` | 2 | 5 | — | 2 | 2 | — | **11** |
| `fluent_functions.py` | 5 | 5 | 4 | — | 4 | — | **18** |
| `types.py` | 3 | 2 | 2 | 3 | — | — | **10** |
| `cte_builder.py` | — | 1 | — | 5 | — | — | **6** |
| `patterns/retrieve.py` | — | — | — | 2 | — | 4 | **6** |
| `property_scanner.py` | — | 1 | — | 1 | 1 | — | **3** |
| `operators.py` | — | — | — | 1 | — | — | **1** |
| `patterns/temporal.py` | — | — | — | 2 | — | — | **2** |
| `patterns/aggregation.py` | 1 | — | — | — | — | — | **1** |
| `patterns/joins.py` | 1 | — | — | — | — | — | **1** |
| **Total** | **23** | **18** | **6** | **16** | **7** | **4** | **74** |

---

## Notes

### Items Excluded by Remediation Plan (Acceptable Hardcoded Dicts)
The remediation plan explicitly exempts these as CQL/SQL spec constants, not FHIR schema:
- `CQL_TYPE_TO_SQL` (operators.py) — CQL spec, not FHIR
- `PRECISION_LEVELS` / `PRECISION_TRUNCATE_FUNCTIONS` (temporal.py) — ISO 8601 / SQL semantics
- `BINARY_OPERATOR_MAP` / `UNARY_OPERATOR_MAP` (operators.py) — CQL operator semantics

These are counted in the inventory (D10–D12) for completeness but should be deprioritized for remediation.

### Duplicated Anti-Patterns
Several violations appear in both immediate and deferred code paths:
- A14/A17: `.resource` qualification in `_substitute_template` vs `DeferredTemplateSubstitution`
- A15/A18: arg collapse in `_substitute_template` vs `DeferredTemplateSubstitution`
- C5: List-type detection duplicated in 3 locations
- D13/E7: `BP_LOINC_CODES` bridges both schema and library categories

### Phase Priority Alignment
- **Phase A targets** (AST utils): Categories A (23) + B (18) + C (6) = **47 instances**
- **Phase B targets** (FHIR schema): Category D = **16 instances** (minus 3 exempted = 13 actionable)
- **Phase C targets** (library inlining): Categories E (7) + F (4) = **11 instances**
