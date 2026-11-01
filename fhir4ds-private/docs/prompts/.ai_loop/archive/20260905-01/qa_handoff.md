# QA Handoff — Iteration 20 / Domain 12 (medterm4ds Integration) / HISTORIAN

Documented-contract walk re-derived FROM 0.0.3 SOURCE (per directives —
not assuming 0.0.2 behavior):

- **Retired-code policy split**: unchanged in 0.0.3 (hierarchy.py not in
  the 5-file diff); `include_retired=False` default = active-only
  discovery; membership-side retired inclusion via the closure table per
  doctrine. Pinned by the subsumption + in-process tests.
- **NER extract kwargs**: `include_negated/uncertain/historical/family`
  present with unchanged defaults (False); 0.0.3 additions are device
  placement + batching only.
- **Search surface** (search.py): only env-knob addition
  (EMBED_BATCH_SIZE); mode/lexical-hybrid-semantic/count semantics
  unchanged; pinned by unit suites.
- Match grades / userSelected / fhir4ds extension: no upstream change.

**Verdict: CLEAN** — every 0.0.2-verified doctrine carries into 0.0.3
unchanged; the only semantic deltas are additive (device, knobs, perf,
thread-safety).
