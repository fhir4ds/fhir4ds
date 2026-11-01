# QA Handoff - FP-13 HISTORIAN

## Scope

- Chunk: FP-13, FHIRPath N1 Section 6.1 Equality.
- Personality: HISTORIAN.
- Spec source: https://hl7.org/fhirpath/N1/#equality
- Focus: `=`, `~`, `!=`, `!~`; scalar equality, ordered collection equality, empty propagation, Quantity unit/dimension behavior, Date/Time precision and timezone behavior, string equivalence, mixed types, complex equivalence.

## Fresh Probe

- Probe: `.temp/qa/fp13_historian_probe.py`
- Log: `.temp/qa/fp13_historian_probe.log`
- Backend coverage: separate-process native C++ extension and forced Python fallback to avoid DuckDB extension load cross-contamination.
- Result before remediation: 47 cases, 6 failing observations grouped into 2 issues.

## Issues

### QA-001 - Native multi-item equality drops indeterminate singleton results

- Severity: MEDIUM
- Spec grounding: Equality returns empty when either operand comparison is empty; Date/Time equality returns empty for equal shared precision with different precision levels; incompatible Quantity dimensions return empty; `!=` is the converse of `=`.
- Evidence:
  - `(@2012 | @2013) = (@2012-01 | @2013)` expected empty; native returned `false`; fallback returned empty.
  - `(@2012 | @2013) != (@2012-01 | @2013)` expected empty; native returned `true`; fallback returned empty.
  - `(1 'cm' | 2 'cm') = (1 'g' | 2 'cm')` expected empty; native returned `false`; fallback returned empty.
  - `(1 'cm' | 2 'cm') != (1 'g' | 2 'cm')` expected empty; native returned `true`; fallback returned empty.
- Likely root cause: native ordered multi-item `=`/`!=` path calls Boolean-only `fpValuesEqual()` and cannot represent singleton equality's empty/indeterminate result.

### QA-002 - Forced fallback complex equivalence fails for complex child lists

- Severity: MEDIUM
- Spec grounding: Complex equivalence requires all child properties to be equivalent recursively; multi-item collection equivalence is order-independent.
- Evidence:
  - Resource has `objA.coding = [{'code':'A'}, {'code':'B'}]` and `objB.coding = [{'code':'b'}, {'code':'a'}]`.
  - `objA ~ objB` expected `true`; native returned `true`; fallback returned empty/NULL.
  - `objA !~ objB` expected `false`; native returned `false`; fallback returned empty/NULL.
  - stderr shows `TypeError: '<' not supported between instances of 'dict' and 'dict'`.
- Likely root cause: Python fallback `deep_equal()` sorts child lists directly, which fails on lists of dicts and bypasses recursive order-independent equivalence matching.

## Handoff

`evolution.json` has been advanced to `phase: FIX` with both findings recorded as `OPEN`.
