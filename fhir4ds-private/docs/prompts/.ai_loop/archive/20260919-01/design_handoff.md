# Design Handoff — WASM C++ Parity (v0.0.14 "browser-complete")

**From:** Feature Designer | **To:** Construction Engineer | **Plan:** `docs/architecture/plans/FEATURE_WASM_CPP_PARITY.md` (v2.1)

## Summary

Port 10 translator-reachable Python-only CQL UDFs to C++ (`cqlDivide`,
`CQLMessage`, `coding_matches`, `coding_matches_exact`, `fhirpath_in_valueset`,
`cqlChildren`, `cqlDescendants`, `cqlDateTimeAdd`, `ratioCompare`,
`ConceptToListCode`) so the no-Python WASM/browser surface executes translated
CQL. Delete 3 dead Python registrations (`ConvertQuantity`, `cqlDateTimeSubtract`
incl. its `_temporal_utils.py:269` whitelist entry, `cqlNormalizeTZ`). Reconcile
WeeksBetween/MillisecondsBetween casing (delete Pascal spellings, ADD camelCase
Python regs — forced-Python leg needs them; native leg is a no-op).

## How refined

1. Draft v1 (loop dir FEATURE_PLAN_DRAFT.md) from first-principles research of
   all 13 function locations, registrations, translator references.
2. Architecture self-audit (ARCHITECT_REVIEW.md): 8 falsifiable invariants
   (INV-1..INV-8), skeptical notes S-1..S-8.
3. Second-opinion review (APPROVE-WITH-CONDITIONS; recorded in plan §6):
   7 conditions adopted after source verification — most materially:
   - cqlDateTimeSubtract has a translator whitelist ref (`_temporal_utils.py:269`) — delete in same commit
   - Pascal WeeksBetween/MillisecondsBetween deletion breaks the forced-Python leg — keep defs, register camelCase
   - ConvertQuantity has 3 direct-SQL test callers — edit them to quantityConvert
   - fhir_loader.py native-mode macro `fhirpath_in_valueset AS in_valueset(...)` (fhir_loader.py:1268-1271) shadows the new C++ fn — must reconcile
   - no-Python harness leaks a Python cqlDivide via register_all_macros (macros/math.py:170-177) — identity assertions via duckdb_functions() required
   - ratioCompare/cqlDateTimeAdd delegate to Python-preferred-authority functions (ToQuantity/dateAddQuantity) — composite parity tests over the known-divergent input classes
   - native CQLMessage parity leg is vacuous on macro-bearing cons — test on LOAD-only con

## Engineer's ordered steps (12)

See plan §4. Critical build/deploy doctrine: dual-target rebuild (native +
`make wasm_eh`, emsdk 3.1.56 at /home/jmontavon/emsdk); wasm binaries to BOTH
`web/wasm-demo/public/extensions/` AND `web/cql-clinic/public/extensions/`;
md5 parity build==bundles==deployed per target. Gates: run_all.py 2832/2832,
wasm-demo playwright (+`10.0 / 3.0` playground case), cql-clinic 3 lessons
(cqlDivide repro must pass).

## Approval

WAIT_FOR_USER_APPROVAL gate WAIVED per USER_DIRECTIVES auto-advance doctrine
(2026-09-07). Second-opinion verdict recorded; conditions incorporated, not
adopted silently.
