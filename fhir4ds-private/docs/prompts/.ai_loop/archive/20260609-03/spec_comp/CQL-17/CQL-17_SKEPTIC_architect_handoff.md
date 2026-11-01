# Architect Handoff: CQL-17 SKEPTIC

Golden standard written to `.temp/architect/golden_standard.md`. The fix is
architecturally acceptable: direct helper null semantics are corrected at the
public UDF boundary, the official `Interval[null, null]` compatibility path is
localized to the `properly included in` translator branch, and no
measure/profile/resource-specific logic was introduced.

Issue status:
- `QA-001` is VERIFIED. No new architecture findings were logged.

QA audit:
- QA was sufficient for SKEPTIC scope. The probe attacked null-value vs
  null-bound intervals, open integer/decimal singleton boundaries,
  union composition, Quantity width conversion, incompatible Quantity units,
  and precision uncertainty across forced Python fallback, native-loaded, and
  no-Python C++ paths. `RETRY_QA` is not needed.

Validation retained:
- Fresh probe PASS.
- CQL-17/no-Python focused pytest 6/6.
- Interval part1/2/3 plus WASM/C++/translate gate 31/31.
- Official interval XML 412/412.
- Full conformance 2822/2822.
