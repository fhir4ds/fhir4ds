# QA Handoff - FP-04 SKEPTIC

## Scope

Fresh run for SPEC COMPLIANCE CHUNK FP-04, FHIRPath section 5.2 Filtering and Projection:
`where(criteria)`, `select(projection)`, `repeat(projection)`, and `ofType(type)`.

Spec source verified against the official HL7 FHIRPath continuous-build source:
https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

Relevant normative reading:
- Scoped functions define exactly which variables are available while evaluating expression parameters.
- `where(criteria)` and `select(projection)` evaluate per item with `$this` and `$index`.
- `repeat(projection)` evaluates per item with `$this`; the spec notes `$index` is undefined and not set during repeat iteration.
- `ofType(type)` requires a type specifier that resolves to a model type.

## Probes

Fresh probe:
- `.temp/qa/fp04_skeptic_fresh_probe.py`

Focused commands:
- `python3 .temp/qa/fp04_skeptic_fresh_probe.py`
- `timeout 10s python3 - <<'PY' ... native a.repeat($index) probe ... PY`
- `timeout 5s python3 - <<'PY' ... forced fallback a.repeat($index) probe ... PY`

## Hypotheses Tested

- Scoped `defineVariable()` state could leak across `select()` or `repeat()` item iterations.
- Root-level `where(criteria)` could diverge from chained `.where(criteria)` for FHIR choice values.
- `repeat()` could de-duplicate by identity instead of FHIRPath equality.
- `ofType(type)` validation could be masked by empty sources or malformed type specifier shape.
- Public native/fallback UDFs could disagree on row-resilient empty/NULL behavior for invalid FP-04 calls.
- SKEPTIC extension: `repeat()` might incorrectly expose `$index` despite the current spec saying it is undefined and not set.

## Findings

### QA-001 - HIGH - OPEN

`repeat(projection)` incorrectly binds `$index`.

Evidence:
- Native/C++ returns public empty/NULL for `a.repeat($index)` only after the native infinite-loop guard, while `fhirpath_is_valid('a.repeat($index)')` remains true.
- Forced Python fallback does not complete under `timeout 5s` for `a.repeat($index)` because each queued item receives a new `$index`, so the projection keeps producing unseen values.

Expected:
- Per FHIRPath section 5.2 scoped-function semantics, `repeat(projection)` sets `$this` for each item. `$index` is undefined and not set for repeat iteration. Top-level `a.repeat($index)` should evaluate the projection to empty and terminate; nested repeat should preserve any outer scoped `$index` instead of replacing it with a repeat-local counter.

## Clean Areas

The fresh parity probe found native/fallback matches for:
- `where()` strict criteria over FHIR choice values.
- `select()` projection flattening and scoped variable isolation in the tested cases.
- `repeat()` recursive projection de-duplication over equal child objects and numeric equality.
- `ofType(Resource)`, `ofType(DomainResource)`, concrete resource filtering, unknown-type validation, missing type argument, invalid arity, and quoted type arguments.
