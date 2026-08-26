WORK SUMMARY & KNOWN ISSUES (EXTENDED)
=====================================

Last Handoff Log: Phase 1 completed; central AST helpers in place, dual AST/SQL context partially implemented, FunctionInliner present but needs hardening; listing detailed known issues and prioritized remediation steps for Phase 2/3.

Context
-------
This document summarizes the current state of the CQL→SQL transpiler remediation work, the highest-priority runtime failures observed while executing measures (CMS124, CMS139, CMS144, CMS165), their root causes, and concrete next steps. The core architectural mandate remains: operate on CQL AST nodes (not rendered SQL), remove hardcoded FHIR/CQL knowledge, and inline function bodies via AST-based inliner.

Detailed Known Issues
---------------------
1) CMS124: Binder Error due to string addition operator
   - Symptom (exact DB error):
     "Binder Error: No function matches the given name and argument types '+(VARCHAR, VARCHAR)'. You might need to add explicit type casts."
   - Evidence (SQL snippet):
     "... (getvariable('patient_resource') AS VARCHAR), 'birthDate') + fhirpath_text(NoCervixProcedure.resource, 'performed'..."
   - Root cause: Translator emitted a binary `+` operator between two VARCHAR operands. DuckDB treats `+` as numeric addition; string concatenation must use `||` or a concat function. This emanates from an AST-level typing/dispatch bug where string concatenation in CQL is mapped to '+' without type-awareness or proper SQL operator mapping.
   - Fix direction: Ensure AST BinaryOp nodes carry type information or resolve operand types during translation; map CQL string concatenation to SQL concat (|| or concat) and/or insert explicit CASTs. Add unit tests asserting correct operator selection for heterogeneous operand types.

2) CMS139: Missing included-definition / Catalog Error
   - Symptom (exact DB error):
     "Catalog Error: Table with name Hospice.Has Hospice Services does not exist!"
   - Evidence (SQL snippet):
     "SELECT p.patient_id, (SELECT * FROM \"Hospice.Has Hospice Services\") AS value FROM _patients..."
   - Root cause: Included definitions (library-level named queries/CTEs) were referenced in generated SQL but not registered/ordered into the final WITH clause. Additionally, name normalization and quoting may mismatch how definitions are stored vs referenced.
   - Fix direction: Ensure all included definitions parsed from libraries are stored as ASTs in the translator context and emitted as top-level WITH-CTEs in the correct order before any query referencing them; unify naming/quoting conventions and add tests for included-definition resolution.

3) CMS144: Execution hang / long-running SQL generation
   - Symptom: Translating/executing CMS144 caused the run to hang (process did not complete within expected time); earlier sessions indicated recursion/stack risks.
   - Root cause: FunctionInliner currently performs depth-first inlining without robust detection of recursive cycles or an inlining depth cap. Additionally, earlier code paths synthesized Python inspect.Signature/Parameter objects from AST metadata, leading to potential recursion and RecursionError in dispatch paths.
   - Fix direction: Construct a function-call graph at library-load time; compute SCCs to detect recursion groups. Do not attempt full inlining for mutually-recursive groups — either skip inlining for those functions or inline only with strict depth limits. Replace inspect.Signature synthesis with lightweight DTOs (name, param list, default) and add cycle detection in translator front-end.

4) Residual string-based AST inspections and regex usage
   - Symptom: Several code sites still inspect rendered SQL text (to_sql()) or use regex to detect AST patterns; this is fragile and violates design principles.
   - Example problematic files/constructs found in audit: translator.py (multiple locations), expressions.py, fluent_functions.py, types.py, cte_builder.py, property_scanner.py.
   - Root cause: Historical pattern of pragmatic fixes using SQL string heuristics rather than AST-introspection.
   - Fix direction: Replace all .to_sql() substring checks and regex-based detections with ast_utils helpers (select_has_column, ast_has_node_type, collect_cte_references, ast_references_name). Add unit tests proving equivalence.

5) Hardcoded FHIR / QICore dictionaries and mappings
   - Symptom: Multiple files contain static maps that encode FHIR structure and QICore library semantics (e.g., RESOURCE_TYPE_VALID_COLUMNS, PROPERTY_CHAIN_COLUMNS, CHOICE_TYPE_COLUMNS, COMPONENT_CODE_TO_COLUMN, STATUS_FILTERS, BP_LOINC_CODES).
   - Root cause: Lack of dynamic StructureDefinition ingestion and dynamic library AST parsing; shortcuts were used to get functional results quickly.
   - Fix direction: Implement FHIRSchemaRegistry (load StructureDefinition JSON), derive choice/element suffixes and valid properties dynamically, and extract constants/status/code lists from parsed library ASTs (not in Python code constants). Stage removal of fallbacks and validate with existing measures.

6) Context stores SQL strings but lacks AST definitions
   - Symptom: Many transformation stages consult context.definitions which contains SQL strings; logic inspects these strings to detect patterns and decide behavior.
   - Root cause: Context initially designed to be SQL-first; AST-first approach was not wired end-to-end.
   - Fix direction: Introduce context.definition_asts alongside context.definitions (SQL). Populate ASTs during translation so logic can use structured AST introspection rather than string parsing. Convert callers incrementally and keep dual storage until full migration is verified.

7) Parser limitations: Temporal operators and other structured expressions parsed as opaque strings
   - Symptom: Translator relies on regex/string parsing of temporal specifiers; leads to fragile logic and incomplete semantics (affects B7/B8 in plan).
   - Fix direction: Extend grammar to emit structured TemporalOperator AST nodes (with fields for quantity, unit, direction, precision). Update translators to use these nodes directly.

8) FunctionInliner robustness
   - Symptom: Missing SCC detection, no depth-limiting, insufficient diagnostics on failed inlining.
   - Fix direction: Build call-graph, detect SCCs and report them; add a default inlining depth limit and a per-library configuration option; generate clear diagnostics when inlining cannot proceed (and fallback to leaving a function call node in AST rather than a raw body SQL template).

9) Typing and SQL operator mapping
   - Symptom: Generated SQL mixes numeric and string operators incorrectly (e.g., '+') and assumes DuckDB overloads.
   - Fix direction: Ensure AST expression nodes carry type hints (STRING, NUMBER, DATE, TIMESTAMP, INTERVAL, QUANTITY). Perform target-dialect operator selection and type-aware casting at AST→SQL emission time.

10) Testing gaps & measure-driven discovery
   - Symptom: Unit tests cover many cases but end-to-end measure translation surfaced errors not caught earlier (missing included definitions, SQL dialect mismatches, inliner recursion). The current integration harness uses the DuckDB extension and a set of small FHIR resources for each measure which exposed those runtime issues.
   - Fix direction: Expand integration tests to include representative resources for each measure; add targeted tests for included-definition resolution and string vs numeric operator mapping.

Files of primary interest
-------------------------
- cql-py/src/cql_py/translator/expressions.py
- cql-py/src/cql_py/translator/cte_builder.py
- cql-py/src/cql_py/translator/fluent_functions.py
- cql-py/src/cql_py/translator/types.py
- cql-py/src/cql_py/translator/function_inliner.py
- cql-py/src/cql_py/translator/translator.py
- cql-py/src/cql_py/translator/ast_utils.py (new / to be expanded)
- fhirpath-rs/ (if applicable) and any StructureDefinition JSONs loaded by FHIRSchemaRegistry

Prioritized Next Steps (Actionable PRs)
--------------------------------------
PR-1 (Tier 1, low risk, ~3h): Replace all .to_sql() substring checks with ast_utils helpers; small, surgical changes across several files.
PR-2 (Tier 2, low risk, ~4h): Add ast_utils helpers: ast_references_name(), collect_cte_references(), is_fhirpath_call(); add unit tests.
PR-3 (Tier 1/3, medium risk, ~6h): Replace inspect.signature synthesis with lightweight DTOs and add cycle guard; fix sites causing RecursionError.
PR-4 (Tier 4, medium risk, ~8h): Dual storage in context (definition_asts) and migrate consumers to query ASTs not SQL strings.
PR-5 (Tier 6, medium risk, ~1-3 days): Implement FHIRSchemaRegistry and replace hardcoded choice/column maps (iterative rollout per resource type).
PR-6 (Tier 7+5, high risk, multi-day): Harden FunctionInliner: call-graph, SCC detection, depth limits; progressively remove body_sql templates by registering library ASTs.
PR-7 (parser, medium-high risk): Add structured TemporalOperator to parser, update translators accordingly.

Acceptance criteria for next milestones
--------------------------------------
- After PR-1/PR-2: No .to_sql() or regex-based checks left in top-level translator logic; unit tests pass.
- After PR-3: RecursionError resolved and CMS144 translation no longer hangs during AST phases.
- After PR-4: Context.definition_asts populated and used by all checks that previously inspected SQL text.
- Final acceptance (post PR-6/PR-7): All 4 measures (CMS124, CMS139, CMS144, CMS165) translate, run, and produce semantically-equivalent SQL with zero runtime errors; full pytest suite green.

Immediate tasks to start now
---------------------------
1. PR-1/PR-2: Sweep for .to_sql() usages and replace with ast_utils equivalents; small tests.
2. PR-3: Replace inspect.Signature/Parameter synthesis with DTOs and add cycle detection around function handling code paths.
3. Add targeted unit tests reproducing the CMS124 '+' VARCHAR failure (translation → SQL generation verifies operator mapping) and CMS139 included-definition missing case.

Notes & diagnostics
-------------------
- The two explicit DB error snippets above are captured from recent runs and should be used in unit/integration tests to reproduce the exact failures.
- Where possible, prefer AST-based small repro test cases instead of full-measure runs so iteration is fast.

Contact / Ownership
-------------------
- Implementation Agents: execute PRs 1–6; ensure unit tests and measure regressions are run in CI.
- Principal Architect: review each PR for architectural compliance (no SQL-string heuristics, no hardcoded libraries, proper AST inlining patterns).

End of summary.
