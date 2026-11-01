# Architect Handoff — FP-06 EXPLORER (launch 3), iteration 1 (2026-08-17)

## Structural audit

Diff scope: `fhir4ds/fhirpath/engine/invocations/misc.py` (iif_macro scope
rewrite, +39/−6 net) and 10 new dual-path regression cases in
`test_conversion_parity.py`. Audited against 5 golden-standard invariants
(see `/mnt/d/fhir4ds/.temp/architect/golden_standard_fp06_explorer3.md`):
snapshot/restore pattern matches sibling iteration functions; the fix
addresses the general criterion-scope class (no test-specific hacks);
native `fn_iif` was the spec-grounded reference (§5.2.9 "remainder of the
expression"), so the Python-only fix with parity tests satisfies the
dual-engine lockstep rule and requires no extension rebuild. No
architecture drift; no new invariants to codify.

## QA quality gate

EXPLORER QA was thorough: 100 dual-path adversarial chaining cases across
all orchestrator-briefed angles, spec-verified via the N1 §5.5.2 table and
official fixtures (`1.convertsToBoolean()`→true fixture-pinned; odd-string
boolean representations; multi-item criterion doctrine). One real MEDIUM
parity bug found and fixed; one LOW edge characterized and deferred with a
documented recommendation. No veto (RETRY_QA not set).

## Issues

- QA-001 (MEDIUM, RESOLVED, verified iter 1): fallback iif criterion
  defineVariable scope. Archived to ARCHIVE_LOG.md.
- QA-002 (LOW, DEFERRED): JSON-null root resource parity
  (`arraify(None)` → [] vs native singleton-null). Spec silent; needs a
  root-context null-semantics decision; both partial fixes leave a
  `type().name` divergence.

## Recommended fix order (future)

1. QA-002 root-context null semantics (only if a consumer ever stores JSON
   `null` resources; otherwise leave documented).
2. None other from this launch.

## Handoff compression

EXPLORER launch 3 probed §5.5.1–§5.5.3 with chained adversarial cases
(iteration contexts, iif-in-repeat/select with defineVariable, Quantity
conversions, odd-string booleans, Unicode digits, criterion corners,
conversion-fed arithmetic) — 100/100 dual-path after one MEDIUM fix:
fallback `iif_macro` now evaluates the criterion in the caller's scope so
criterion-defined variables persist for the remainder of the expression
(matching native `fn_iif` and §5.2.9), while branch-defined variables stay
branch-scoped. Conformance held 2832/2832; tests 40/40 parity file, 76/76
scope selection. Chunk FP-06 remains closed with cumulative tally:
SKEPTIC clean (2 INTENDED), HISTORIAN 3 MEDIUM fixed, EXPLORER 1 MEDIUM
fixed + 1 LOW DEFERRED.
