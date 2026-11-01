# Architect Handoff — SOF-VD-07 EXPLORER (iteration 1)

## Golden-standard check (repeat chunk)
Invariants audited against the fix:
1. ViewDefinition must not special-case FHIR element shapes; generic FHIRPath
   navigation feeds `fhirpath_repeat`. — HELD: fix is in the FHIRPath core,
   not the viewdef generator.
2. Shadow-node provenance must be explicit, not inferred from data shape. —
   NOW HELD (was the defect): `_is_shadow_extension` flag set at synthesis;
   key-shape heuristic removed from both `apply_parsed_path` filters.
3. Dual-engine lockstep (native vs Python fallback). — RESTORED: native
   evaluator already returned extension-only elements (verified via
  `allow_unsigned_extensions` LOAD); the Python fallback was the divergent
   engine. No native change needed; binary md5 unchanged and matched.
4. No silent fallbacks / test-driven hacks. — HELD: flag-based, general to
   the class of inputs; no fixture-specific logic.
5. Fixtures outrank prose. — HELD: official repeat.json (19 fixtures) and the
   full 144/144 ViewDef suite still pass.

## QA Enforcer Gate
QA was NOT lazy: probed 12+ boundary areas (12-path unions, 1000-wide,
3000/6000-deep, alternating repeat/forEach stacks, contained ofType
recursion, collection=true, %rowIndex interplay, unionAll branches,
subtree-isomorphism dedup, SQL shape, where-expressions, 3D nesting) and
root-caused a real HIGH bug to a one-line invariant violation. No RETRY_QA.

## State summary
Iteration 1: QA-001 HIGH RESOLVED (extension-only element drop in Python
FHIRPath navigation corrupting repeat row counts; shadow-flag fix + 7
regression tests); QA-002 LOW INTENDED (O(n^2) deep-tree repeat inherent to
value-dedup). Zero open non-terminal CRIT/HIGH/MEDIUM issues.
min_iterations=1 reached → CLEAN exit eligible.

## Validation
ViewDef 144/144; master gate 2832/2832; fhirpath+viewdef pytest 1440 passed
(6 pre-existing failures in uncommitted FP-18 native parity tests — absent at
HEAD, numeric-only, out of chunk scope). Extension binary md5
57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages.

## Recommended fix order (next launches / outer orchestrator)
1. FP-18 uncommitted native div/mod parity tests (6 failing) — reconcile with
   the deployed binary or fix native long-division before release.
2. Optional perf: incremental/structural dedup for fhirpath_repeat to remove
   O(n²) subtree serialization on deep trees.
