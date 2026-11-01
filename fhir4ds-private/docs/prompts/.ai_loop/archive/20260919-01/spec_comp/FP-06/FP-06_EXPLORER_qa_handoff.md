# QA Handoff — FP-06 EXPLORER (launch 3), iteration 1 (2026-08-17)

Chunk: FHIRPath §5.5.1 iif, §5.5.2 Boolean Conversion, §5.5.3 Integer
Conversion. Personality: EXPLORER (chained/adversarial probing).

## What was probed (100 dual-path cases, `.temp/qa/fp06_explorer3_2026_08_17/probe.py`)

Native extension vs forced Python fallback, both via `SELECT fhirpath(?, ?)`
(+ `fhirpath_is_valid`), per the FP-04 EXPLORER probe-harness doctrine:

- Conversions inside iteration contexts: `select`/`where`/`repeat` over
  heterogeneous components, `$this`/`$index` with `toInteger()` arithmetic
  and `iif($index = 0, ...)`.
- iif nested in `select`/`repeat` fixpoints with `defineVariable` scoping
  (before/criterion/then/else/after-iif, nested iif, per-item variables).
- Conversions of Quantity values (literal + JSON `valueQuantity.value`,
  quantity comparisons/arith feeding `convertsToInteger`/`convertsToBoolean`).
- `toBoolean()` feeding `and`/`or`/`xor`/`implies`/`not()` on odd strings.
- `convertsTo*` on collections (multi-item, heterogeneous, empty).
- Unicode digit forms in `toInteger` strings (Arabic-Indic, fullwidth, Roman,
  fractions, U+2212 minus, mixed-script).
- iif criterion corners (empty, singleton non-Boolean, multi-item,
  dedup'd `true|true`, navigation criterion, 3-deep nesting, laziness).
- Conversion results feeding arithmetic/comparison chains.

## Spec verification performed

- N1 §5.5.2 table: `1.convertsToBoolean()` → true is pinned by official
  fixtures (`testIntegerLiteralConvertsToBoolean`); `'tRuE'/'1'/'yes'/'yEs'`
  forms are in the N1 possible-representations table (case-insensitive) —
  both engines agree; NOT bugs.
- `iif(1|2, ...)` → empty + is_valid=false (multi-item criterion error);
  `iif(true|true, ...)` → 'a' because `|` dedups to a singleton.
- `false or {}` → empty per the §4.3 truth table.

## Findings

- QA-001 (MEDIUM, OPEN→RESOLVED by FIX phase): fallback `iif_macro` hid
  criterion-defined `defineVariable` variables from the taken branch and the
  remainder of the expression; native fn_iif (and §5.2.9 "remainder of the
  expression") keeps criterion vars in the expression's main scope.
  2 PARITY failures pre-fix; 100/100 post-fix.
- QA-002 (LOW, DEFERRED): JSON-null root resource divergence — Python core
  `arraify(None)` → empty collection vs native singleton-null root. Only
  observable when a root-chained function's implicit focus is the resource
  (`defineVariable('x',1).select(%x)` → native ['1'], fallback []). Spec
  silent, no fixture; wrapper null→{} fixes 8/9 probes but `type().name`
  still diverges. Filed, not fixed (blast radius).

No CRITICAL/HIGH issues. Conformance baseline confirmed 2832/2832 pre-fix.
