# QA Handoff — CQL-04 EXPLORER (iteration 1, 2026-08-20)

Chunk: CQL 1.5 Logical Operators — And, Or, Not, Xor, Implies.
Personality: EXPLORER. Workspace: `/mnt/d/fhir4ds/.temp/qa/cql04_explorer2_2026_08_20/`
(probe.py, probe2..5.py, prec_probe.py, cql.g4+generated ANTLR parser).

## Spec anchor (verified EMPIRICALLY against the official grammar, not prose)

Downloaded HL7/cql v1.5.3 `cql.g4`, generated an ANTLR 4.13.1 parser, and
parsed the probe expressions directly (`prec_probe.py`). Locked truths:

- **`not` binds TIGHTER than between/set/inequality/timing/equality/
  membership/and/or/xor/implies** (notExpression alternative listed before
  them; ANTLR earlier-alternative = higher precedence). `not 5 in {1,2}`
  parses as `(not 5) in {1,2}` — i.e. a type error, NOT `not (5 in {1,2})`.
  Same for `not 1 = 2`, `not 3 < 2`, `not A between 1 and 10`.
- `not` binds LOOSER than `is [not] null/true/false` and `is`/`as`:
  `not X is null` = `not (X is null)`; `not [Condition] is null` likewise.
- `not exists X` = `not (exists X)`; `not not true` fine.
- `implies` chains LEFT-associative: `(false implies false) implies false`.
- `xor`/`or` share one left-assoc tier; `and` tighter than or/xor;
  `implies` loosest.

**The CQL-04 HISTORIAN launch misread ANTLR alternative ordering
(earlier=looser) and moved `not`'s operand to the equality tier — that fix
was in the wrong direction and is now QA-001.**

## Probes (all dual-path Python supplements vs C++ extension; parity held on every case)

Covered: 3VL truth tables with null; implies/xor chains and mixed
precedence; absent FHIR Boolean fields (active/deceased) through retrievals;
Coalesce/`is null`/`is not null` compositions under and/or/not; division
(`1/0`) and malformed-DateTime guards under and/or/implies (short-circuit
equivalence — all null-guarded, no SQL errors); case expressions; tuple
selectors (incl. null Boolean elements feeding logic); Boolean define
aliases; query-let aliases; retrieve where-clause logic.

## Findings

### QA-001 (HIGH, OPEN) — `not` operand precedence too loose
`not 1 = 2` → True; spec parse `(not 1) = 2` → must be a translation error.
Four manifestations (=/</in/between). Introduced by HISTORIAN QA-001 fix.
Both paths (single parser). See evolution.json for evidence.

### QA-002 (HIGH, OPEN) — multi-`when` case collapses to a later literal-true when
`case when Patient.active then 1 when true then 3 else 2 end` lowers to bare
`3 AS resource`; earlier matching whens discarded. First-when-true and
non-constant whens are correct.

### QA-003 (HIGH, OPEN) — Boolean define alias is text-typed in logic
`define F: Patient.active` materializes via `fhirpath_text` (VARCHAR);
`F and true` → all True, `not F` → all False, `F or false`/`F xor true`
wrong for false/null patients. Violates the Boolean-only-at-boundary
doctrine. Direct inlining and query-let aliases are correct.

### Verified correct (no issue)
- Full 3VL corners incl. `null implies false`→null(→FALSE surface),
  `false implies null`→true; xor 3-operand left-assoc chains; and>or=xor>
  implies precedence; `true or false implies false`→false.
- Null→FALSE population-surface doctrine (pinned, INTENDED).
- Division/DateTime error guards: null-propagating, no eager-eval SQL
  errors, both paths.
- Tuple selectors and query-let aliases feed logic correctly.
- py-vs-cpp parity on every probe.

Handing off to Remediation Engineer.
