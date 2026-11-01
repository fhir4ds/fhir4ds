# FP-02 EXPLORER — Architect Handoff (2026-08-16, spec-compliance campaign)

**Iteration 1, EXPLORER personality.** Chunk: FHIRPath §4.2–§4.5.
Golden standard: `.temp/architect/golden_standard_fp02_explorer_iter1.md`
(9 invariants). Issue summary: 3 RESOLVED+VERIFIED (QA-001 MEDIUM, QA-002
MEDIUM, QA-003 LOW), 2 DEFERRED (QA-004 LOW, ARCH-001 LOW). Zero non-terminal
CRITICAL/HIGH/MEDIUM issues.

## Structural health: SOUND

- The launch diff (registry removal, sniffing removal, metadata/hierarchy
  alignment, validity-list additions, extension rebuild) removes one silent
  guessing heuristic rather than adding one, keeps type knowledge in the
  canonical data files plus their native mirror, and adds no layer crossings
  or test-driven special cases. All 9 golden-standard invariants hold.
- Empirical audit: 500-case randomized differential corpus over the is/as/
  type() surface (8 resources × 25 fields × 20 specifiers × 4 forms) — 2
  divergences, both the pre-existing `Composition.type.type().name` complex-
  type naming gap (native 'BackboneElement' vs fallback 'object'; R4:
  CodeableConcept), filed as ARCH-001 DEFERRED. Nothing regressed.
- Validation gate: fhirpath package pytest **1720/1720**; full conformance
  **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — the
  PROC_VALIDATION baseline held exactly.

## QA Enforcer Gate: PASS (no RETRY_QA)

QA ran 236 dual-path probe cases plus targeted drill matrices, grounded every
finding in the N1 spec text or official R4 fixtures before filing, and
correctly REJECTED two tempting would-be findings by reading fixtures (the
FHIR-vs-System namespace split pinned by testType11–14, and `{}.iif(true,...)`
returning the branch per testIif7). All three filed issues reproduced and were
fixed at root cause.

## Recommended fix order (deferred backlog)

1. QA-004 — decide the unknown-function chaining direction (native
   continue-with-empty vs fallback whole-expression error); ViewDef resilience
   convention makes this a design decision, not a bugfix.
2. ARCH-001 + the `.date`/temporal residual — resource-qualified type metadata
   completeness; the generated `models/r4/path2Type.json` (7,705 entries)
   already contains the truth for both surfaces to consume.

## State

- `evolution.json`: issues tombstoned (details in ARCHIVE_LOG.md); QA-004 and
  ARCH-001 terminal DEFERRED; workflow advanced to CLEAN exit (iteration 1 ≥
  min_iterations 1, no non-terminal CRITICAL/HIGH/MEDIUM).
- Chunk handoffs archived to `spec_comp/FP-02/FP-02_EXPLORER_*`.
- AGENTS.md and GLOBAL_KNOWLEDGE.md updated with this launch's discoveries.
