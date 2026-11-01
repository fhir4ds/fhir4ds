# QA Handoff — CQL-13 (SKEPTIC), iteration 1

Chunk: CQL 1.5 Date/Time Operators Part 1 — Add (DateTime+Quantity), After/Before
precision of, Date()/DateTime() constructors, Component From, Difference in
precision between, Duration in precision between.

Spec source verified: CQL 1.5 STU4 Appendix B §8.1–8.8 (cql.hl7.org/2019May
09-b-cqlreference.html), fetched in full this session.

Method: pre-existing suite test_datetime_part1_parity.py (15/15 green), then two
fresh adversarial batteries through per-expression translate_cql + DuckDB
execution on BOTH the native/C++ connection and the Python-supplement-only
connection: /mnt/d/fhir4ds/.temp/qa/cql13_dt1/{probe1.py (117 cases), probe2.py
(61 cases)}.

Results:
- Calendar-aware Add truncation (Jan 31 + 1 month -> Feb 28/29), precision
  truncation of results to operand precision (61 minutes on hour-precision
  operand -> +1 hour; 1.5 days on day-precision date -> +1 day, decimal
  fraction ignored per spec), UCUM units ('a','mo','wk','d','min','s','ms'),
  timezone preservation, null propagation: all conformant, py==cpp.
- After/Before with precision incl. all spec examples verbatim
  (AfterIsTrue/False/UncertainIsNull/IsNull, Before ditto), timezone-respecting
  comparisons, Date/DateTime mixed operands: conformant.
- Date()/DateTime() constructors incl. all partial forms, out-of-range
  components (static -> translation error, dynamic -> SQL NULL), null
  component propagation: conformant (CQL-03 doctrines hold).
- Component From for every precision keyword on Date/DateTime/Time incl.
  timezoneoffset (decimal, Z -> 0.0), uncertain-precision -> null: conformant.
- Duration vs Difference distinctness, negative results, timezone
  normalization, uncertainty intervals ([0,11]-style per spec examples):
  conformant (string-typed integers and interval-JSON uncertainty are
  established repo conventions).
- py vs cpp agreed on every probe output (both engines share the same two
  defects below).

Issues (see evolution.json):
- QA-001 (HIGH): difference in weeks uses truncated day-span/7 (duration
  semantics) instead of counting Sunday-first-day week boundaries (§8.7).
  @2024-01-04 -> @2024-01-10 returns 0, spec requires 1.
- QA-002 (MEDIUM): Date value + sub-day quantity unit (hour/minute/second/
  millisecond) silently no-ops (returns input unchanged) instead of null
  (§8.1 unit restriction for Date operands); also affects Subtract.
