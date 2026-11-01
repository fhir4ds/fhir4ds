# QA Handoff — CQL-13 (HISTORIAN), iteration 1

Chunk: CQL 1.5 Date/Time Operators Part 1 — Add (DateTime+Quantity),
After/Before precision of, Date()/DateTime() constructors, Component From,
Difference in precision between, Duration in precision between.

Personality: HISTORIAN (spec-compliance verifier). Spec source verified
live: CQL 1.5 STU4 Appendix B §8.1–8.8 (cql.hl7.org/2019May
09-b-cqlreference.html), fetched in full this session.

Method: re-verified the SKEPTIC launch's two fixes regression-free (week
difference Sunday-boundary counting; Date + sub-day unit → null), then
hunted NEW divergences with a fresh 31-case dual-engine battery plus an
11-case scoping battery (.temp/qa/cql13_hist/probe3.py and inline),
targeting surfaces the SKEPTIC pass did not cover: sub-day Difference
semantics, Time+Quantity arithmetic, per-type precision allowlists,
convert-and-truncate at sub-unit quantities.

Re-verification of prior fixes: week difference (Sun boundaries,
Duration-vs-Difference distinctness) and Date unit restriction hold on
both engines; Add convert-and-truncate finer cases (90 min on hour
precision → +1h, 90 s on minute precision → +1m, 1500 ms on second
precision → +1s) all conformant.

New findings (see evolution.json):
- QA-001 (HIGH): sub-day Difference (hours/minutes/seconds/milliseconds)
  used §8.8 Duration truncation math instead of §8.7 boundary counting.
  difference in hours between @2024-01-01T10:30 and @2024-01-01T12:15
  returned 1, spec requires 2 (hour marks 11:00 and 12:00 crossed).
  Both engines; legacy differenceIn{Hours,Minutes,Seconds} UDFs shared it.
- QA-002 (MEDIUM): Time + week/day units (keyword and UCUM) silently
  no-opped (returned input unchanged) instead of null; §8.1 restricts
  Time quantity units to hours/minutes/seconds/milliseconds. Year/month
  already returned null — incomplete allowlist, same defect family as the
  SKEPTIC's Date fix.
- QA-003 (LOW, DEFERRED): week-precision After/Before/same-as evaluate to
  null instead of being rejected (spec: "comparisons involving weeks are
  not supported"; `week from` IS rejected — inconsistent), and per-type
  precision allowlists (hour precision on Date operands, day/week units on
  Time operands in duration/difference) are enforced leniently. No wrong
  non-null value is ever produced.

NOT A BUG registry additions (verified conformant): Time + sub-day units
incl. modulo-midnight wrap (@T00:30 - 90 minutes → T23:00) and
convert-and-truncate (@T10 + 90 minutes → T11); timezone-normalized
sub-day Difference (@12:00-07:00 vs @12:00-05:00 → -2); sub-day
duration/difference on Date-only literals surfaces the repo's uncertainty
interval convention ([0,47] hours), pinned as accepted leniency under
QA-003.
