# GLOBAL RULES

Compact durable invariants every `.ai_loop` role should read before strategy or edits. `GLOBAL_KNOWLEDGE.md` contains recent discoveries and historical detail; read it selectively when relevant.

---

## Platform-Neutral Operation

- Use available capabilities, not specific tool names: shell, file search, editor patching, browser/search, local docs, or delegated agents.
- If delegated agents are unavailable, execute the target role sequentially in the current context.
- Persist progress in state files. Chat output is secondary.
- Completion is determined by state files, especially `evolution.json.workflow == null` plus a non-null `exit_reason`.

---

## Orchestration

- Read `STATE_SCHEMA.md` before interpreting or mutating loop state.
- Never stop before `config.min_iterations` unless there is a critical environmental blocker.
- After `config.min_iterations`, clean exit is allowed when no non-terminal CRITICAL/HIGH/MEDIUM issues remain.
- Only run to `config.max_iterations` by default when `config.exhaustive_mode` is true; otherwise `max_iterations` is a degraded-exit guardrail.
- Every evolution iteration must produce `qa_handoff.md`, `engineer_handoff.md`, `architect_handoff.md`, and `GLOBAL_KNOWLEDGE.md` updates.
- `code_review_findings.md` belongs to `code_review`; commit message drafts belong to `scribe`.
- Feature design owns draft, architecture self-audit, refinement, final FDD, and approval handoff.
- Shared working tree: only one session at a time may edit a given shared source file (e.g. `evaluator.cpp`, `operators.py`, `functions/`, model metadata). Before editing, verify your prior markers are still present; sibling sessions have silently overwritten whole-file fixes.
- A native fix is not landed until the deployed extension is verified: binary mtime > source mtime, md5-matched across repo bundle, site-packages, and the ~/.duckdb cache (which serves stale binaries), and the fix re-verified through a reloaded connection.

---

## FHIRPath and C++ Extension Invariants

- Use `fpValuesEqual()` for semantic equality. Do not compare through `toString()`.
- Type guards must account for `JsonVal` opacity. Prefer `effectiveType()`, `isNumericType()`, and `getNumericValue()` over raw `val.type` checks.
- Functions accepting only specific input types must reject invalid types instead of coercing through `toString()` or `toNumber()`.
- Save and restore loop scope (`index_context_`, `chain_defined_vars_`, `defined_variables_`) around evaluator calls inside iteration functions.
- Lazy functions such as `aggregate` and `iif` must not eagerly evaluate all arguments.
- Date/time parsing must enforce strict digit counts, ranges, precision semantics, and leap-year rules.
- JSON null navigation generally skips null values, but `children()` must preserve null children.
- Unicode string operations must use UTF-8-aware helpers for character positions.
- Resource-type-prefixed fast paths must call `ComputeSegStart()` on the already-parsed root, fall through on type misses, and guard when the prefix consumes all segments.
- Never dereference `yyjson_val*` after freeing its owning document.
- Dual-engine changes must land in lockstep: every FHIRPath semantic change is implemented in BOTH the Python fallback and native evaluator.cpp, with a native-vs-fallback parity test, before the chunk closes.
- After any `evaluator.cpp` change, rebuild and redeploy the bundled `fhirpath.duckdb_extension` (repo bundle and user site-packages); source-only edits do not affect package behavior.
- Error-message contracts are coupled: any new execution-type-error message must be added to both `_is_valid_empty_result_error` (udf.py) and the native `FhirpathIsValidFunction` acceptance lists so sibling messages classify identically.
- Official fixtures outrank spec prose and engine parity in both directions; a missing `<output>` in fixture XML is an expected-EMPTY assertion, never "unspecified".
- When adjudicating spec severity or structure, the machine-readable artifact (StructureDefinition XML, released-IG zip, reference-implementation source) outranks HTML spec pages and mandate prose; re-derive expected values from live normative text before logging — probe-expectation errors outnumber real bugs roughly 3:1.
- `fhirpath_is_valid()` validates expression validity, not whether sample evaluation returns a non-empty result. Valid incompatible comparison/arithmetic expressions may evaluate to empty/NULL and must still be valid; unresolved type specifiers, wrong type-function arity, and malformed temporal literals remain invalid.

---

## CQL Translator Invariants

- Avoid `SQLRaw` and `to_sql()` in the middle of translation pipelines unless explicitly justified by a boundary API.
- Do not use silent fallbacks that mask schema, context, or translation errors.
- Externalize resource types and recurring magic strings through canonical constants.
- Preserve translator layering: parsing, semantic AST, SQL generation, and DuckDB execution should not reach across each other's boundaries.
- CQL interval and temporal boundary behavior must be spec-grounded and covered by focused tests.
- Every numeric value serialized into a FHIRPath/CQL literal (constants, parameter defaults, generated literals) must satisfy the literal grammar: no exponent notation (plain fixed-point Decimal), Integer within 32-bit literal range, and JSON parsing with `parse_float=Decimal` (never `json.loads` float rounding).

---

## Model Knowledge Must Be Data-Driven

- FHIR resource, profile, terminology, measure, and implementation-guide knowledge should come from schema metadata, registries, configuration files, generated model artifacts, terminology resources, or measure/profile packages.
- Generic runtime logic must not embed QICore, US Core, HEDIS, CMS, or other implementation-guide-specific assumptions.
- Avoid translator/evaluator branches such as `if resource_type == "Observation"` unless they are part of a documented adapter boundary or generated metadata consumer.
- Do not hardcode measure IDs, patient IDs, fixture IDs, population names, profile URLs, ValueSet URLs, CodeSystem URLs, OIDs, or clinical code lists in generic logic.
- Choice type behavior (`value[x]`, `effective[x]`, `onset[x]`, etc.) should be resolved from FHIR metadata, not handwritten resource-specific field lists.
- Profile URL to resource type or profile behavior must be registry-based, loaded from StructureDefinitions or curated metadata, not ad hoc string matching.
- Terminology is data, not code: code may resolve terminology resources, but clinical membership lists and value set content belong in terminology/config inputs.
- Missing schema, profile, or terminology metadata should fail clearly or return a typed unsupported result. Do not guess silently from strings.
- Tests, examples, docs, generated schema files, parser grammar, and user-provided source mappings may contain concrete resource/profile strings. The risk is behavior-changing hardcoding in generic runtime paths.

---

## ViewDefinition Invariants

- Built-in FHIRPath variables are canonically defined in `fhir4ds/viewdef/constants.py:FHIRPATH_BUILTIN_VARIABLES`.
- Do not duplicate the built-in variable set in generator logic.
- `forEachOrNull` must preserve parent rows when the target path is absent.
- Dual-language UDF families (e.g. the cqlUncertain* age-uncertainty set) must ship with one shared fail-closed parse doctrine and fallback-path parity tests at birth; runtime native-wins selection does not excuse an untested or divergent Python twin (REV-012).

---

## Validation

- `PROC_VALIDATION.md` is the source of truth for baseline commands and pass counts.
- Keep validation output compact. Prefer delegated/background validation when available; otherwise filter output to summaries.
- A fix is not complete until the reproducer passes and relevant baseline validation has not regressed.
- If a fix attempt fails or creates a regression, trigger `PROC_DEEP_RESEARCH.md` before a second blind attempt.
