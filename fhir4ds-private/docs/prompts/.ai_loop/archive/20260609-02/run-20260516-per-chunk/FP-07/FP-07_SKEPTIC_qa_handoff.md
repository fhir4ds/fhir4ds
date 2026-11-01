# QA Handoff — FP-07 SKEPTIC

Scope: FHIRPath §5.5.4 Date Conversion, §5.5.5 DateTime Conversion, §5.5.6 Decimal Conversion.

Spec checked: HL7 FHIRPath §5.5.4-§5.5.6 says `toDate()`/`convertsToDate()` accept Date, DateTime, or Strings convertible to Date; `toDateTime()`/`convertsToDateTime()` accept DateTime, Date, or Strings convertible to DateTime; `toDecimal()`/`convertsToDecimal()` accept Integer, Decimal, Boolean, or Strings matching `(+|-)?\d+(\.\d+)?`. Multi-item input is an error to the calling environment; empty input returns empty.

SKEPTIC hypotheses tested:
- Native decimal conversion may over-accept because source uses `std::stod`.
- Leading/trailing whitespace may be accepted in native or helper paths.
- Exponent notation may be accepted despite not matching §5.5.6.
- Incomplete decimal forms such as `1.`, `.1`, and `-.1` may be accepted.
- Date and DateTime conversions may mishandle invalid dates, DateTime-to-Date, Date-to-DateTime, or multi-item input.
- Native and forced Python fallback may diverge for public DuckDB UDFs.

Finding:
- `QA-001` MEDIUM SPEC_VIOLATION: native C++ `toDecimal()` and `convertsToDecimal()` accepted non-spec String formats (`1e2`, `1.`, `.1`, `-.1`, ` 1`) while the Python fallback correctly returned empty/false. Reproducer: `PYTHONPATH=. python3 .temp/qa/fp07_skeptic_probe.py` before remediation showed native values such as `['100.0']`/`true` where fallback returned empty/false.

No Date/DateTime bugs were found in this pass. Date invalidity, DateTime-to-Date extraction, Date-to-DateTime partial precision, and multi-item row-level resilience matched between native and forced Python fallback.
