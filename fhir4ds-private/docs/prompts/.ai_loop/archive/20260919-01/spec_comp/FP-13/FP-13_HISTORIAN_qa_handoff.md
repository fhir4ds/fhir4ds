# QA Handoff — FP-13 launch, iteration 1 (HISTORIAN)

Chunk: FHIRPath §6.1 Equality — =, !=, ~, !~ (Quantity, Date/Time, String,
Decimal, collections, complex types).

## What was probed (dual-path: native extension vs forced Python fallback)
Probes: /mnt/d/fhir4ds/.temp/qa/fp13_historian_2026_08_17/probe.py (85 cases),
probe2.py (51), plus two inline round-3/4 matrices. Spec text verified against
the cached N1 spec adoc (§6.1 verbatim, incl. DateTime timezone examples,
calendar-vs-definite quantity pins, Whitespace lexical category).

- SKEPTIC QA-001 fix regression re-check: `1.0 ~ 1.0001`, `1 ~ 1.4`,
  `0 ~ 0.4`, `1.0 ~ 1.06` → true in both engines; multi-item lambda path
  `(1.0 | 2.0) ~ (1.0001 | 2)` true; JSON-native path
  `valueQuantity.value ~ 1.0` true. Fix holds, no regression.
- Spec §6.1 verbatim DateTime timezone equality examples: all correct
  (`@2017-11-05T01:30:00.0-04:00 = @2017-11-05T00:30:00.0-05:00` true, etc.).
- Spec Date/Time equality precision examples (incl. EMPTY vs false split
  between = and ~): all correct.
- Calendar vs definite durations: `1 year = 1 'a'` EMPTY — pinned FP-01
  fixture doctrine (official fixtures outrank prose); `~` true. Holds.
- Quantity = conversion (cm/m, g/mg, in_i, kg), invalid-unit EMPTY, offset-
  temperature EMPTY (pinned): all correct.
- Multi-item: `=` order-dependent, `~` order-independent, length mismatch
  false, complex-type recursive equality/equivalence (HumanName case-fold
  under ~ only): all correct.
- Decimal `=` trailing zeros, negative zero, 0.1+0.2=0.3, mixed
  Integer/Decimal: correct.
- Type mixing per §5.5 conversion table (Boolean=1 EMPTY, 1='1' EMPTY,
  5='5 cm' EMPTY, 5 '1' = 5 true): correct.
- Date-vs-String coercion → true: pinned FP-01 JSON-convenience doctrine.
- Integer literals > 2^31-1 → empty: pinned FP-06 doctrine.

## Findings
- QA-001 (MEDIUM, OPEN): String `~` whitespace class too broad and
  engine-divergent. Spec §6.1.2: whitespace equivalence uses ONLY the
  Whitespace lexical category = {tab, space, LF, CR}. Both engines normalize
  the full Unicode whitespace set (NBSP U+00A0, U+0085, U+1680, U+2000-200A,
  U+2028/9, U+202F, U+205F, U+3000): `'a b' ~ 'a b'` → true (expected
  false). Additionally a native-vs-fallback parity break: U+001C-001F are
  whitespace for `str.isspace()` (fallback true) but not the native set
  (native false). Sites: evaluator.cpp normalizeEquivalentString (~line
  1507); fhir4ds/fhirpath/engine/invocations/equality.py normalize_string
  (line ~173).

Everything else clean across ~180 fresh cases; zero other parity diffs.
