# QA Handoff — FP-06 (FHIRPath §5.5.1 iif, §5.5.2 Boolean Conversion, §5.5.3 Integer Conversion)

Launch: spec-compliance campaign, iteration 1, personality SKEPTIC (2026-08-17).

## Method
- Spec source: fetched normative text from hl7.org/fhirpath/N1 §5.5.1–§5.5.3
  (conversion tables, regex grammar `(\+|-)?\d+`, case-insensitivity note,
  lazy-evaluation requirement for iif).
- Dual-path probe (209 cases): native `fhirpath.duckdb_extension` connection vs
  forced Python fallback (`duckdb.__version__="0.0.0-forced-python-fallback"`),
  both through `SELECT fhirpath(?, ?)` + `fhirpath_is_valid(?)`.
  Probe: `/mnt/d/fhir4ds/.temp/qa/fp06_skeptic_2026_08_17/probe.py`
  (results JSON alongside). Run with `PYTHONPATH=/mnt/d/fhir4ds`.
- Official R4 fixture cross-check (40 conversion + 18 iif fixtures in
  `fhir4ds/fhirpath/duckdb/tests/compliance/r4/tests-fhir-r4.xml`).
- Direct helper API audit: `fhir4ds/fhirpath/duckdb/functions/conversion.py`
  `to_integer` / `to_boolean` (source-read + spot execution).
- Full conformance suite: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held; no code changes made.

## Result: PASS=209 FAIL=0 — zero parity diffs, zero spec violations

### Verified clean
- **toBoolean string table** (both engines): full N1 table `'true','t','yes','y','1','1.0'` → true,
  `'false','f','no','n','0','0.0'` → false, case-insensitive ('TRUE','False','YES','No','T','Y'),
  invalid ('maybe','2','-1','1.5','2.0','01','+1',' 1','1 ','', 'true false') → empty.
- **toBoolean numeric/boolean**: Boolean passthrough; Integer/Decimal 1/1.0/0/0.0;
  2, -1, 2.0, -1.0 → empty; Quantity → empty; literals match data fields.
- **convertsToBoolean**: true for every convertible representation (including the
  false-family and mixed case); false (not empty) for non-convertible; empty input → empty.
- **toInteger**: string grammar `(\+|-)?\d+` exactly (no whitespace, no '1.0', no '1e3',
  no '0x1', no bare '+/-'); Boolean true→1/false→0; Integer passthrough; Decimal → empty;
  Quantity → empty; 32-bit bounds enforced ('2147483647'/'-2147483648' OK,
  '2147483648'/'-2147483649'/20-digit → empty).
- **convertsToInteger**: mirrors toInteger; false for Decimal/Quantity; empty input → empty.
- **Multi-item inputs**: error → empty at UDF boundary, is_valid parity on both surfaces.
- **iif (§5.5.1)**: true/false/empty/null criterion; omitted otherwise → empty when not
  taken; LAZY evaluation proven via dead-branch `1/0` in both directions
  (`iif(false,1/0,'safe')`→'safe', `iif(true,'safe',1/0)`→'safe'); nested iif;
  collection results; empty-focus `{}.iif(true,...)` (fixture testIif7);
  boolean-convertible criterion via `.toBoolean()`; criterion from data fields;
  `iif(arr,...)` multi-item criterion consistent.
- **Official fixtures**: all 40 conversion + 18 iif fixture expectations matched
  (incl. `2147483647.convertsToInteger()`=true, `-1.convertsToInteger()` execution-invalid,
  `iif(true,true,1/0)`=true, `iif('non boolean criteria',...)` execution-invalid).
- **Cross-chaining**: toBoolean feeds `and`; toInteger feeds arithmetic and toString
  round-trips; iif-inside-where; toInteger(iif(...)).

### Doctrine pins (NOT A BUG — do not "fix")
- `convertsToInteger('2147483648')` → **false** (not the prose-literal regex-only
  reading) in BOTH engines: a string outside the 32-bit Integer range is treated as
  not convertible, consistent with `toInteger` returning empty for the same input.
  No official fixture pins overflow strings; engine consistency + Integer range
  semantics govern. Logged as QA-001 LOW / INTENDED.
- `iif('non boolean criteria', ...)` → execution error in the strict core
  (fixture testIif6 invalid="execution") and non-boolean singleton criteria follow
  the pinned §4.5 singleton doctrine at the wrapper boundary (FP-02 doctrine
  re-confirmed). Logged as QA-002 LOW / INTENDED.

## Handoff to FIX
No CRITICAL/HIGH/MEDIUM issues; no source changes required. Remediation is a no-op.
