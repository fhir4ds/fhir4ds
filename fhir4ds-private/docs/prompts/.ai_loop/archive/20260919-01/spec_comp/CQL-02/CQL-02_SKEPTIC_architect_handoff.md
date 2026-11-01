# Architect Handoff — CQL-02 Clinical Types, iteration 1 (2026-08-19)

## Structural health: SOUND for this chunk

Golden standard: `.temp/architect/golden_standard_cql02_skeptic.md`
(7 falsifiable invariants for clinical-type handling across
parser → translator → DuckDB execution).

- All four HIGH fixes satisfy the invariants: equivalence normalization is
  centralized in one key helper; Concept folding reuses
  `_static_clinical_value_object`/`_normalize_static_clinical_code` (no
  duplicated clinical knowledge); the define-alias inlining sits at ONE
  choke point (top of `_translate_identifier`) before promotion/alias/CTE
  resolution — closing the two-site divergence class that
  `_classify_definition_ref` was created to prevent.
- No hardcoded clinical constants introduced; codesystem resolution goes
  through context registries (terminology-as-data invariant clean).
- No SQLRaw/to_sql mid-pipeline; no new silent fallbacks (the
  dynamic-member Concept path deliberately defers to runtime construction,
  documented in code).
- Dual-backend parity verified for every fixed surface (Python fallback and
  native C++ produce identical results through the deployed extension; no
  rebuild needed since all fixes are translator-layer).

## Issue summary
- 4 HIGH SPEC_VIOLATION → RESOLVED (QA-001 equivalence casing,
  QA-002 Concept named-code double-serialization, QA-003 .codes list
  semantics, QA-004 static clinical define-alias dangling CTE)
- 1 LOW INTENDED (QA-005 structural CodeSystem membership)
- 1 MEDIUM TEST_HYGIENE → RESOLVED (QA-006 stale CQL-01-doctrine test
  expectations)

## QA Enforcer Gate
QA (SKEPTIC) was NOT lazy: 31 dual-backend definition-level cases +
full-pipeline execution + direct spec-text verification; found 4 real HIGHs
the prior 2026-Q2 campaign missed. No RETRY_QA.

## Validation
Conformance 2832/2832 (ViewDefinition 144, FHIRPath 935, CQL 1706, DQM 47);
clinical type parity 18/18; related parity files 56/56; CQL unit+parity
4992 passed.

## Recommended fix order (next engineer, out of this chunk)
1. Generic scalar literal define aliases (`define S: 'hello'; define T: S`
   → Binder error): same patient-id-less CTE shape mismatch family as
   QA-004; route through a primitives-chunk launch (CQL-01 scope).
2. Audit remaining `_classify_definition_ref` callers for other
   literal-valued CTE shapes (string/Integer/Boolean) once (1) lands.

## Exit
Clean-exit criteria met at iteration 1 (min_iterations=1): zero non-terminal
CRITICAL/HIGH/MEDIUM issues. workflow → null, exit_reason → CLEAN.
Details archived in ARCHIVE_LOG.md; tombstones in evolution.json.
