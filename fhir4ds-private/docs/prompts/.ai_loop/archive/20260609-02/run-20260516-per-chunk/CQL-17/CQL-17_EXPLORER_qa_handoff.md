# QA Handoff — CQL-17 EXPLORER

Status: ISSUES_FOUND

Spec focus: CQL Interval Operators Part 3: point from, properly includes/included in, same/same-or-before/same-or-after precision, size, start, starts, union, width.

Spec citations used:
- CQL Reference v1.5.3 Appendix B says `point from` extracts the single point from a unit interval and null-propagates null input.
- `Start` uses effective interval boundary semantics: open low returns successor; closed low returns the low value.
- `Size` is `(end - start) + point-size`; `Width` is `end - start`; neither is defined for date/time intervals.
- `Union` returns the interval spanning the earliest starting point and latest ending point when intervals overlap or meet.
- CQL Decimal has a minimum step size of `10^-8`.

Probe written:
- `.temp/qa/cql17_explorer_probe.py`

Fresh findings:
- `QA-001` MEDIUM: forced Python/native-loaded `intervalUnion` can widen open integer boundaries when serializing union results, causing downstream `intervalStart`, `intervalContains`, and `intervalEquals` to disagree with no-Python C++ and CQL effective-boundary semantics.
- `QA-002` MEDIUM: decimal interval part-3 helpers are not aligned. No-Python C++ formats decimal successor/predecessor with insufficient precision, while Python fallback size/width/pointFrom do not consistently use effective decimal endpoints and point-size.

Representative failing command:

```bash
python3 .temp/qa/cql17_explorer_probe.py
```

First failure observed:

```text
AssertionError: union_open_low_does_not_widen python: expected False, got True
```

Required remediation:
- Align Python `intervalUnion` output with effective/open-bound semantics so composed helpers do not include excluded endpoints.
- Align decimal `intervalStart`, `intervalEnd`, `pointFrom`, `intervalWidth`, and `interval_size` across forced Python fallback, native-loaded registration, and no-Python C++.
