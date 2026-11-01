# QA Handoff - FP-13 SKEPTIC

## Scope

FHIRPath N1 §6.1 Equality operators: `=`, `~`, `!=`, `!~`, with emphasis on quantity, date/time, and string behavior. Tested native DuckDB C++ extension and forced Python fallback (`duckdb.__version__ = "0.0.0-forced-python-fallback"`).

## Spec Basis

Verified against https://hl7.org/fhirpath/N1/ §6.1:
- `=` returns empty when either operand is empty; multi-item equality is order-dependent; quantity equality compares compatible dimensions/units, with calendar vs definite durations above seconds unequal.
- `~` treats two empty collections as equivalent; multi-item equivalence is order-independent and uses item equivalence; string equivalence ignores case and normalizes whitespace; quantity equivalence allows compatible units and calendar/definite duration equivalence.
- `!=` and `!~` are converses of `=` and `~`.

## Hypotheses Tested

1. Multi-item `~` might use raw string/set comparison instead of semantic item equivalence.
2. Native C++ and Python fallback might diverge for compatible-unit quantities.
3. Calendar duration equality (`year` vs `'a'`) might incorrectly propagate empty instead of false.
4. Date/time partial precision might incorrectly return true for `~` or non-empty for `=`.
5. `!~`/`!=` might not mirror the corresponding positive operators.

## Findings

- `QA-001` HIGH: multi-item equivalence does not consistently reuse item equivalence. Native C++ fails compatible-unit quantity equivalence; both native and fallback fail whitespace/case-normalized string multi-item equivalence.
- `QA-002` HIGH: forced Python fallback returns empty for `1 year = 1 'a'` and `1 year != 1 'a'`; spec expects false and true respectively.
- `QA-003` MEDIUM: multi-item calendar/definite duration equivalence fails in both backends.

## Evidence

Probe script: `.temp/qa/fp13_probe.py`

Observed:
- `(1 'mg' | 2 'mg') ~ (0.002 'g' | 0.001 'g')`: native false, fallback true, expected true.
- `(1 'mg' | 2 'mg') !~ (0.002 'g' | 0.001 'g')`: native true, fallback false, expected false.
- `stringsA ~ stringsB` for `["alpha beta","Gamma"]` vs `[" gamma ","ALPHA\tBETA"]`: both false, expected true.
- `1 year = 1 'a'`: native false, fallback empty, expected false.
- `(1 year | 1 second) ~ (1 'a' | 1 's')`: native false, fallback empty, expected true.

## Recommended Fix Direction

Route all multi-item equivalence through the same semantic item-equivalence function used by singleton `~`, with order-insensitive matching and duplicate accounting. Avoid `toString()`/raw sorting/`Counter(str(...))` as the semantic comparison key. In Python equality, calendar-vs-definite year/month equality should return `False`, not `None`, so `!=` becomes `True`.
