# Golden Standard — CQL-02 Clinical Types audit (2026-08-19)

Scope: CQL 1.5 Code/CodeSystem/Concept/ValueSet/Vocabulary types across
parser → translator → DuckDB execution (Python fallback + native C++).

Invariants audited (falsifiable):

1. CQL clinical values (Code/Concept/ValueSet/CodeSystem) are STRUCTURED
   values: every construction path (selector, instance, ToConcept, named
   declaration, define alias) must produce the same canonical JSON shape;
   no path may embed already-serialized JSON as a string inside another
   clinical value.
2. Code/Concept operator semantics must come from the CQL 1.5 spec, not
   analogy: `=` uses tuple equality (display/version sensitive, null on
   different components); `~` uses string equivalence on code+system
   (case/locale-insensitive, whitespace-normalized) and Concept code
   intersection; `~` is total (always true/false except null-vs-empty).
3. Property access on structured clinical values (`X.code`, `X.codes`)
   must respect member types — list-valued members yield List<Code>, so
   list-aware consumers (Count, in, distinct) behave correctly.
4. Static clinical literal definitions are library CONSTANTS: references
   must inline or otherwise resolve without inventing patient-correlated
   CTEs that do not exist.
5. Terminology is data, not code: membership resolution may consult
   terminology tables/UDFs, never hardcoded clinical lists; without
   terminology data, static resolution is structural and documented.
6. No SQLRaw/to_sql mid-pipeline; no silent fallbacks masking translation
   errors; dual-backend parity (Python fallback vs native C++) for every
   clinical surface.
7. Translator layering: clinical knowledge lives in translator mixins +
   context registries (codes/codesystems/valuesets), not in parser or
   DuckDB UDF internals.

## Audit findings
- All four engineer fixes (QA-001..004) land within these invariants:
  normalization is centralized in `_cql_string_equivalence_key`; concept
  folding reuses `_static_clinical_value_object`/`_normalize_static_clinical_code`
  (no duplicated key logic); the define-alias inlining runs at a single
  choke point (top of `_translate_identifier`) before promotion/alias/CTE
  resolution, so all reference paths agree (invariant 4; fixes the
  prior two-site divergence class called out in `_classify_definition_ref`).
- Remaining architectural gap (logged, out of chunk): generic scalar
  literal defines (`define S: 'hello'; define T: S`) still emit
  patient-correlated lookups against patient-id-less CTEs — same shape
  mismatch family; belongs to the CQL primitives (CQL-01) surface.
- `_fold_static_concept_instance` falls back to the generic json_object
  path for dynamic members — deliberate runtime evaluation, not a silent
  error mask (acceptable; documented in code).
- No new hardcoded clinical constants introduced; codesystem lookups go
  through `self.context.codesystems` registries (invariant 5/7 clean).
- QA quality: SKEPTIC probed 31 dual-backend definition cases + full
  pipeline execution + spec text verification; no happy-path-only laziness.
  No RETRY_QA.

## Empirical validation
Conformance 2832/2832 (ViewDefinition 144, FHIRPath 935, CQL 1706, DQM 47);
clinical parity 18/18; related parity files 56/56 after fix.
