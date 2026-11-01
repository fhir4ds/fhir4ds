# QA Handoff — FP-09 HISTORIAN (iteration 1, 2026-08-17)

Chunk: FHIRPath §5.6.1–§5.6.5 String Manipulation (Search) — indexOf,
substring(start[,length]), startsWith, endsWith, contains.

## Method
- Dual-path probe `.temp/qa/fp09_historian2_2026_08_17/probe.py` (~60
  checks): native extension (LOAD by absolute path) vs forced Python
  fallback (`duckdb.__version__` forced + `register_fhirpath(con) is
  False` asserted), both via `SELECT fhirpath(?, ?)`, plus direct-helper
  module checks and `fhirpath_is_valid` parity (single-argument form).
- HISTORIAN mandate: re-verify the SKEPTIC `index_of` helper fix AND hunt
  NEW divergence angles (not a rerun of the SKEPTIC's 164 cases).

## SKEPTIC fix re-verification (PASS)
- `index_of` helper present with §5.6.1 semantics, registered in
  `STRING_FUNCTIONS`, engine parity on spec examples + resource fields.

## New angles probed (all engine parity OK)
- Sourced-call argument focus: `s.indexOf(field)`, `$this` arguments,
  sibling-field arguments (`'Chalmers'.startsWith(name.family)`),
  count()-computed substring start — native outer-focus arg evaluation
  matches fallback.
- Astral plane / combining: U+1D400 substring/indexOf/endsWith, 4-byte
  emoji pairs, start==len boundary on astral strings, decomposed
  combining sequences.
- substring length matrix: len 0 / negative → `''`; `{}` length ignored
  (§5.5.2 override); overrun clamping incl. astral; start=len+1 → `{}`.
- is_valid: 7 arity/type forms — parity on both surfaces.
- Spec ground truth: live N1 fetch failed (server error); grounded on the
  engines' shared conventions + the normative example set already pinned
  by the SKEPTIC launch's live-spec fetch (fixture-backed).

## Issues
- QA-001 (MEDIUM, OPEN → RESOLVED in this launch): direct helpers in
  `fhir4ds/fhirpath/duckdb/functions/string.py` diverged from engine
  semantics — `starts_with`/`ends_with`/`contains` crashed with raw
  `TypeError` on empty (None) argument collections (engines return `{}`)
  and on non-String args (engines raise typed errors); `substring(None)`
  crashed; `substring(1, -2)` returned `{}` while both engines return
  `''`. 4th instance of the "exported helper API forgotten" family.

## Convention correction
- The SKEPTIC pin "negative start/length → {}" was half wrong: negative
  START → `{}` but negative/zero LENGTH → `''` (empty STRING) in both
  engines. AGENTS.md corrected.

## Verdict
Zero non-terminal CRITICAL/HIGH/MEDIUM issues after the fix (which
landed in the same launch's FIX phase).
