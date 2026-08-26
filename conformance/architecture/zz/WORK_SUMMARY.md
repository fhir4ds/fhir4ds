Work Summary — Architectural Remediation (current snapshot)

Generated: 2026-03-02T23:18:00Z

1) What was done (high level)
- Completed 66 of 74 anti-pattern remediations (89%).
- Major refactors: AST-first utilities (ast_utils.py), FHIR schema registry (fhir_schema.py), dynamic fluent-function loader and AST-based inliner (fluent_function_loader.py / FunctionInliner), context upgrade to store ASTs (definition_asts).
- Eliminated string-based SQL inspection and regex-heavy template transformations; replaced with structural AST checks and schema-driven lookups where possible.

2) Known issues (expanded detail)

A. CMS144 — RecursionError in inspect/enum
- Symptom: RecursionError while constructing or consuming Python inspect/enum objects: "_ParameterKind(kind)" recursion exceeded.
- Diagnostic observations:
  - Error occurs when converting parsed CQL function signatures/parameter metadata into Python runtime signature objects (inspect.Parameter/Signature).
  - Stack trace points to code that synthesizes Python signatures from AST-derived ParameterDefinition objects.
  - Reproduced consistently on the CMS144 measure harness; it was present before remediation work.
- Likely root-causes:
  1. Circular references in the synthesized signature (e.g., parameter annotation or default referencing an AST node that references back into signature creation path).
  2. Passing non-primitive objects (AST nodes or registrar objects) into inspect.Parameter fields where enums/primitive values are expected, triggering nested inspect calls.
- Immediate mitigation:
  1. Stop constructing inspect.Parameter/Signature objects from AST directly — use plain DTOs (dicts) containing name/type/default strings.
  2. Add defensive cycle detection when converting AST → runtime objects (use _visited id set).
  3. Add unit tests that build small, synthetic ParameterDefinition objects that previously triggered the recursion and assert safe conversion.
- Estimated time to fix: 1–2 days (investigation + code change + tests)

B. CMS165 — Intermittent hang during full SQL generation
- Symptom: Comprehensive measure generation sometimes hangs indefinitely when inlining large numbers of fluent functions.
- Diagnostic observations:
  - Unit/integration parsing tests pass, but end-to-end SQL generation blocks during AST-based inlining.
  - Instrumentation shows function inliner enters deep recursion on certain library functions.
- Likely root-causes:
  1. Cyclic function inlining (A inlines B, B inlines A) without cycle detection.
  2. Excessive inlining depth for legitimate recursive functions (e.g., fold-like functions) without a bounding strategy.
- Immediate mitigation:
  1. Implement inliner call-graph analysis and detect SCCs; prevent mutual inlining or emit controlled placeholders instead.
  2. Limit inlining depth via a configurable threshold and emit clear diagnostic errors if exceeded.
  3. Add unit tests to detect mutual recursion and ensure inliner fails gracefully.
- Estimated time to fix: 1–3 days

C. Temporal operator parsing (B7/B8) — parser-level tech debt
- Symptom: Temporal operator constructs are parsed into opaque operator strings and downstream code uses regex on rendered SQL to extract semantics.
- Root-cause: Current CQL parser lacks a dedicated AST node for temporal operators; translator must regex the string to understand semantics.
- Fix: Extend the CQL parser grammar to produce structured AST nodes (TemporalOperator with fields: direction, magnitude, unit, anchor, precision). Update translator to use the AST node.
- Estimated time to fix: 3–5 days

D. Retained fallback/optimizations (deliberate)
- Items retained for safety/performance and not considered violations to remove immediately:
  - CHOICE_TYPE_COLUMNS precomputed definitions (D3)
  - _CHOICE_TYPE_COLUMN_NAMES optimization (D5)
  - PROPERTY_CHAIN_COLUMNS (D7)
  - property_to_column_name() fallback map (D8)
  - BP_LOINC_CODES (D13) kept until valueset resolution is fully in place
  - infer_fhirpath_function() heuristics (D15)
- Migration path: iterate measures to replace each retained item with schema-driven generation and remove fallback once covered by tests.
- Estimated combined migration: 1–3 weeks (incremental across measures)

3) Where to find the detailed remediation doc (already generated)
- Detailed remediation and known-issues analysis: /mnt/d/duckdb-fhirpath/docs/ARCHITECTURAL_REMEDIATION_SUMMARY.md
- Short operational summary and next steps: /mnt/d/duckdb-fhirpath/docs/WORK_SUMMARY.md (this file)

4) Immediate next steps (action plan - short)
- Priority 1: Fix CMS144 recursion by removing inspect.signature usage on AST-derived objects; convert to DTOs + add cycle detection.
- Priority 2: Harden FunctionInliner: build call graph, detect SCCs, guard inline depth, add tests to detect mutual recursion.
- Priority 3: Parser enhancement for temporal operators (B7/B8) — extend grammar and AST nodes.
- Priority 4: Migrate retained fallbacks to FHIR schema/property-scanner results across measures.

5) Commands & repro
- Run all unit tests: `cd cql-py && python3 -m pytest -q`
- Run measure: `python3 /tmp/test_measure.py CMS165 5`
- Enable inliner logs: `COPILOT_LOG_INLINER=1 python3 /tmp/test_measure.py CMS165 5`

6) Estimated effort to complete remaining work
- CMS144 fix: 1–2 days
- Inliner hardening: 1–3 days
- Temporal operator parser: 3–5 days
- Migration of retained fallbacks: 1–3 weeks (incremental)


If you want, I will begin Priority 1 (CMS144 recursion fix) now and update the plan and todos as I make progress.