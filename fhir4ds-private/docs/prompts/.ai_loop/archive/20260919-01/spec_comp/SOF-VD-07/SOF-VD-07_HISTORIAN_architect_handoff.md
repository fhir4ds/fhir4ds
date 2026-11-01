# Architect Handoff — SOF-VD-07, HISTORIAN, iteration 1

## Audit scope
Re-audit of the select.repeat slice after the SKEPTIC iteration's recursion-
budget fix, focused on NEW divergences: expression-typed repeat paths (fixture-
untested but spec-permitted: "A list of FHIRPath expressions"), built-in
variables in repeat paths, error handling parity, cycle-equivalent fixpoints,
null-preservation composition, and dual-engine (native vs Python fallback)
result parity on every probe.

## Findings
- No architectural violations. No fixture-specific or resource-type branching
  in repeat runtime paths; generator/unnest layering intact; validation parity
  between repeat paths and column paths (both reject invalid FHIRPath at
  generate time with typed ValidationError — no silent-empty divergence).
- Dual-engine parity held on 100% of probes (17 view-level probes x 2 engines),
  including union expressions, where-filters, children(), $this fixpoints, and
  Process(S,N) step-3 null preservation under forEachOrNull.
- SKEPTIC's fix verified regression-free (deep-6k, worker-thread path, no
  segfault, suite green). Deeper depths remain compute-bound per documented
  O(n²) doctrine — accepted residual, not architectural debt.
- %resource inside repeat paths binds to the per-node evaluation root on both
  engines (matches reference-impl per-node evaluate semantics); consistent,
  logged as doctrine.

## Gates (fresh, final tree, PYTHONPATH=/mnt/d/fhir4ds)
- ViewDefinition conformance: 144/144 (repeat.json 19/19)
- FHIRPath R4: 935/935 | CQL: 1706/1706 | DQM: 47/47 | OVERALL: 2832/2832
- viewdef pytest: 1186/1186
- fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a — repo bundle
  == ~/.local site-packages (unchanged; no native edits this launch)

## QA Enforcer Gate
HISTORIAN was NOT lazy: 17 fresh view-level probe families (most dual-engine),
fresh official fixtures, fresh master gate, and an independent re-verification
of the prior launch's fix at a depth exercising the worker-thread path. New
spec-permitted-but-fixture-untested surface (expression repeat paths) was
explicitly targeted per institutional memory. **No RETRY_QA.**

## Verdict
Chunk SOF-VD-07 CLEAN at iteration 1 (>= min_iterations=1); zero non-terminal
CRITICAL/HIGH/MEDIUM issues. Recommend clean exit.
