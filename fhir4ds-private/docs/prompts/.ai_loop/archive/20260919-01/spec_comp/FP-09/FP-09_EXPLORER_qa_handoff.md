# QA Handoff — FP-09 EXPLORER (3rd personality), iteration 1

**Chunk**: FHIRPath §5.6.1–§5.6.5 String Manipulation (Search) — indexOf,
substring(start[,length]), startsWith, endsWith, contains.
**Personality**: EXPLORER (chainer/abuser). **Date**: 2026-08-17.
**Probe**: `/mnt/d/fhir4ds/.temp/qa/fp09_explorer3_2026_08_17/probe.py` (82
dual-path checks: native extension LOAD-abs-path vs forced Python fallback,
both via `SELECT fhirpath(?, ?)`; 10 is_valid parity checks). Run with
`PYTHONPATH=/mnt/d/fhir4ds`.

## Result: ZERO parity diffs, ZERO spec violations. No issues filed.

EXPLORER angles probed (fresh vs SKEPTIC/HISTORIAN launches):

- **H1 Chaining**: indexOf feeding substring (incl. indexOf→-1 feeding
  substring → `{}` in both), substring→endsWith composition, startsWith|
  endsWith union filtering via `where($this.startsWith(...) or
  $this.endsWith(...))`, select-of-indexOf over unions, indexOf→count,
  repeat over substring/indexOf projections (fixpoint terminates via `=`
  dedup: `'abc'.repeat($this.substring($this.indexOf('b'), 1))` → `['b']`).
- **H2 Wrong-typed/absent FHIR fields**: object-valued `Coding.code`,
  integer `display`, boolean `multipleBirthBoolean`, absent `valueString`,
  resource-root focus, multi-item `name.given` — all yield the singleton-
  String error → empty at the UDF boundary identically in both engines.
- **H3 Iteration contexts**: select with `$this`/`$index` feeding substring,
  where/exists/all with contains/startsWith criteria, repeat substring
  shrink fixpoints. All correct.
- **H4 Expression arguments**: arguments computed via `+`, `length()`,
  indexOf expressions; empty/multi-item collection args (error → empty
  both); non-String args (Integer/Boolean/Quantity) → empty both.
- **H5 Unicode/long strings**: NFD combining sequences (code-point
  positions correct: `éabc`.indexOf('abc') → 2; substring
  splits combining pairs as code points), NFC-vs-NFD contains correctly
  false (byte/code-point identity, no normalization — correct), ZWJ at
  boundaries, astral-plane startsWith/endsWith, CJK substring, 10k-char
  strings (indexOf/endsWith/substring), empty needles (`''.indexOf('')`→0,
  contains('')→true), case sensitivity, NUL/tab/newline.
- **H6 is_valid parity**: 10 arity/malformed forms — identical on both
  surfaces; chained `indexOf`-inside-`substring` classified valid.

## Probe-harness lessons (no engine bugs)

- `'a'.repeat($this & 'b')` is an **infinite-growth fixpoint** — dedup
  never converges; excluded from probes (both engines grow unboundedly;
  spec-consistent, not a bug).
- 9 initial "expectation" flags were ALL probe-author arithmetic/escape
  errors (native==fallback in every case): `'xyz'.length()-3` is 0;
  `'oh'.indexOf('o')` is 0; `\U0001D400` is NOT a FHIRPath escape (both
  engines treat it as literal ASCII `\U`→`U`-text); repeat projection on
  `'abc'` yields `'b'` not `'bc'` (substring(1,1) is one char).
- Re-confirms the FP-04 EXPLORER doctrine: compare native UDF vs forced
  fallback UDF; never compare against raw `evaluate()` output.

## Exit check

Zero non-terminal CRITICAL/HIGH/MEDIUM issues and `iteration (1) >=
min_iterations (1)` → CLEAN exit eligible pending conformance verification.
