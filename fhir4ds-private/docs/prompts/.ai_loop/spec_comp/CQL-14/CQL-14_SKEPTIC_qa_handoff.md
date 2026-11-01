# QA Handoff — CQL-14 SKEPTIC (DateTime ops Part 2)

## Verdict: CLEAN — 33 fresh dual-path cases (probe1), 0 parity diffs, 6 flags all adjudicated probe-expectation errors

Coverage: Now/Today/TimeOfDay determinism + shapes; Same As / Same Or After / Before /
On Or After / Before [precision] incl. inclusive boundaries; Subtract DateTime−Quantity
(Mar31−1mo=Feb29 clamp; Date−23h→NULL; Time−1day→NULL; T12:00−90min=T10:30);
Time() ctor precision renders (T14:30/T14:30:45/T14:30:45.123; Time(null)→NULL;
Time(14)=@T14); resource-backed rows.

Adjudications (direct re-verification /tmp/opencode/cql14_adj*.py, both engines identical):
1-2. Now() vs Today() comparisons → False (precision mismatch: Now is full-precision+offset
DateTime vs date-only; use `date from Now() = Today()` which → True).
3. same minute as @...:30:45 (differing seconds) → True (precision ignores finer components).
4. @2024-06 same month as @2024-06-20 → True (Y-M only).
5. +05:00-vs-Z same-instant at differing precision → False (precision uncertainty beats
instant equality unless BOTH full precision).
6. years between Today() and Today() → int 0 (checker-form).

Evidence: .temp/qa/speccomp2/cql14_skeptic_probe1.py
