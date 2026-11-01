# QA Handoff - FP-12 HISTORIAN

## Scope

Fresh launch for SPEC COMPLIANCE CHUNK FP-12 with `qa_personality` HISTORIAN.
I used only the current `evolution.json`, current source tree, and the official
HL7 FHIRPath continuous-build source for §5.8 Tree Navigation and §5.9 Utility
Functions.

Spec anchors verified:
- `children()` returns immediate child nodes; child ordering is undefined.
- `descendants()` excludes the input items and is shorthand for
  `repeat(children())`.
- `trace(name, projection)` returns the input collection unchanged; the
  optional projection is evaluated per input item with `$this` and `$index`.
- `now()`, `today()`, and `timeOfDay()` return deterministic values within a
  single expression.

## Fresh Probe

Created and ran:

```bash
python3 .temp/qa/fp12_historian_fresh_probe.py
```

Result: passed, 33 expressions.

The probe compared native DuckDB/C++ registration and forced Python fallback
registration for:
- immediate and recursive tree navigation, including split primitive extension
  hiding, null-valued child preservation through count behavior, duplicate
  complex descendant de-duplication through `repeat(children())`, and >100-level
  deep traversal;
- `trace()` identity, dynamic outer-focus labels, per-item projection scoping,
  `$index` in projection, projection error row resilience, and scope restoration
  after nested `select()`;
- deterministic `now()`, `today()`, and `timeOfDay()` equality within a single
  expression plus public string shape checks;
- invalid signatures for `children`, `descendants`, `trace`, `now`, `today`,
  and `timeOfDay`.

Focused permanent parity suite:

```bash
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q
```

Result: 10 passed.

## Findings

No new issues opened.

Review-10 findings were checked for intersection. The open regex, delimited
identifier, type-specifier, and direct string-substring findings do not touch
FP-12 tree navigation or utility function behavior in this pass.

## Notes for Remediation

No implementation fix is required. Proceed through a no-op FIX phase so the
loop can produce the required engineer and architect handoffs for this launch.
