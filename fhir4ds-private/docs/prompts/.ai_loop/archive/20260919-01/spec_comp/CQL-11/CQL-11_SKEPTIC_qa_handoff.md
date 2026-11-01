# QA Handoff — CQL-11 SKEPTIC (iteration 1)

Chunk: CQL arithmetic operators part 2 (Max/Min, Modulo, Multiply, Negate,
Precision, Predecessor, Power, Round, Subtract, Successor, Truncate,
TruncatedDivide). Probed translation + DuckDB execution on BOTH the Python
supplement path and the native C++ extension path (parity compared).

Verified clean (both engines, spec-conformant): Modulo sign-of-dividend
(-5 mod 3=-2, 5 mod -3=2, -5 mod -3=-2, Decimal mod, mod 0 -> null), Round
half-away-from-zero incl. Round(2.5)=3, Round(-2.5)=-3, Round(2.675,2)=2.68,
null precision, Truncate toward zero -> Integer with out-of-range -> null,
Integer/Long Multiply/Subtract overflow -> null, BIGINT promotion
(2147483647 * 2L -> 4294967294), Negate incl. -(minimum Integer/Long) -> null,
Quantity mod/div/negate/subtract/multiply unit-aware, Predecessor/Successor
for Date/DateTime/Time at component precision + boundary nulls, Power
overflow -> null (int+decimal, function+infix), Power(2,-2)=0.25,
Max/Min aggregates (list + two-arg) null handling, maximum/minimum T limits.

Issues found (all confirmed on both engines where applicable):
- QA-001 HIGH: div lowered through DOUBLE `/` — 0.3 div 0.1 -> 2 (spec 3);
  Long div inexact; Long overflow not null. Fix via exact cqlDivide + typed
  TRY_CAST (see engineer handoff).
- QA-002 MEDIUM: Power underflow -> 1E-8 instead of 0.00000000 (scientific
  text + DuckDB VARCHAR->DECIMAL cast quirk) in BOTH python mathPower and
  native MathPowerFunc output contract.
- QA-003 MEDIUM: Precision(5) py=0 vs native BinderException (translator
  passes raw typed literal; native UDF VARCHAR-only).

Repro scripts: /mnt/d/fhir4ds/.temp/qa/probe*.py
