# QA Handoff: FP-03 SKEPTIC

## Scope

Fresh SKEPTIC pass for SPEC COMPLIANCE CHUNK FP-03, FHIRPath §5.1 Existence:
`empty()`, `exists([criteria])`, `all(criteria)`, `allTrue()`, `anyTrue()`,
`allFalse()`, `anyFalse()`, `subsetOf(other)`, `supersetOf(other)`,
`count()`, `distinct()`, and `isDistinct()`.

Spec source: HL7 FHIRPath continuous-build source `input/pages/index.md`,
§5.1 Existence and scoped-function semantics. The relevant normative behavior:
`subsetOf`/`supersetOf` determine membership using `=`; empty input/default
truth values are documented; `distinct()`/`isDistinct()` also use `=`; and
scoped functions such as `select()`, `exists(criteria)`, and `all(criteria)`
evaluate nested expressions for each current item with `$this`/`$index` set.

## Hypotheses Tested

- Native and fallback could disagree on §5.1 default truth values for empty
  input.
- Boolean aggregate helpers might short-circuit before validating the full
  Boolean collection.
- `distinct()`/`isDistinct()`/set membership could accidentally use string
  equality instead of FHIRPath `=`, especially for Quantity and complex JSON.
- `subsetOf()`/`supersetOf()` arguments could be evaluated in the wrong context
  when called inside scoped functions.
- `fhirpath_is_valid()` could disagree between native and fallback for invalid
  helper arities or data-dependent criteria errors.

## Findings

Found 1 issue.

`QA-001` (`MEDIUM`, `OPEN`): native DuckDB/C++ evaluates `subsetOf()` and
`supersetOf()` argument expressions against the root resource context instead
of the current scoped item when invoked inside scoped expressions. Reproducer:

```bash
python3 .temp/qa/fp03_skeptic_fresh_probe.py
```

Observed mismatches:

- `groups.select(left.subsetOf(right))`: native `['false','false']`; fallback
  and expected `['true','false']`.
- `groups.all(right.supersetOf(left))`: native `true`; fallback and expected
  `false`.
- `groups.select(right.supersetOf(left))`: native `['true','true']`; fallback
  and expected `['true','false']`.

The Python fallback behavior matches the spec because `right`/`left` are paths
relative to the current `groups` item introduced by `select()`/`exists()`/`all()`.

## Validation Run

- `python3 .temp/qa/fp03_skeptic_fresh_probe.py` failed as expected with the
  scoped native/fallback mismatches above.
