# Architect Handoff — FP-12, iteration 1 (2026-08-17)

## Golden standard (chunk-scoped invariants audited)

1. Dual-engine lockstep for FHIRPath semantics (GLOBAL_RULES) — verified: the
   QA-001 fix is Python-only *because the native engine was already correct*;
   parity restored and pinned by regression test.
2. `descendants()` ≡ `repeat(children())` (§5.8.2) — the QA probe enforced
   this equivalence; it is now parity-tested.
3. `children()` must preserve null children (GLOBAL_RULES invariant) —
   verified on both engines (null children serialized and counted).
4. Exported direct helpers must mirror engine semantics (FP-09/FP-11
   doctrine) — QA-002 closed the gap; helper `children(list)` was corrected
   during audit to reduce per item like the engine (initial version returned
   the list itself); extra test added.
5. No silent fallbacks — `children()` raises `FHIRPathError` on unsupported
   types; `trace()` validates the name argument.

## Audit result

- QA-001 fix (`engine/util.py::parse_value` None fall-through): surgical and
  general (fixes the class: any invalid/None-sentinel parse result now falls
  through to structural comparison). Blast radius audited at all 16
  `parse_value` call sites (equality/equivalence/math/toQuantity/toString) —
  all isinstance-guarded; spot-checks (`toQuantity` unitless/unit-bearing,
  `= 120 'mg'`, `~`, `.value`) parity-clean; 1809 fhirpath tests and 2832/2832
  conformance confirm no regression.
- QA-002 module (`duckdb/functions/navigation.py`): layering correct (imports
  engine `FP_Quantity` for unit-aware equality rather than duplicating
  conversion tables — avoids the REV-002 drift family); no hardcoded resource
  knowledge; registered via `NAVIGATION_FUNCTIONS`.

## QA Enforcer Gate

QA was NOT lazy: 57 dual-path evaluation cases + 13 is_valid cases covering
every chunk item, null-preservation, ordering, shorthand equivalence,
determinism, precision shapes, arity/error paths, empty-input corners, and
the direct-helper surface. RETRY_QA not set.

## State hygiene

Issues QA-001/QA-002 RESOLVED (verified in iteration 1); details archived to
ARCHIVE_LOG.md; evolution.json carries tombstones.

## Structural health

No new architecture drift. Recommended fix order: none required; optional
follow-up — long-term delegation of direct helpers to engine
implementations (existing REV-002 family note) covers the new module too.
