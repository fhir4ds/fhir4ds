# Architect Handoff - FP-08 HISTORIAN

Date: 2026-06-12

## Structural Health

Architect audit result: clean. No new architectural findings were opened.

The QA pass found one real FP-08 conversion boundary defect: Quantity
`toString()` could leak host-language scientific notation in native C++ and
forced Python fallback. The remediation is narrow and general: Python
`FP_Quantity` now formats Decimal values using fixed notation while preserving
Decimal scale, and native Quantity rendering now switches to fixed notation
when default stream formatting would emit exponent notation. The fix does not
use `toString()` for semantic equality and does not alter Quantity comparison
logic.

## Issue Summary

- `QA-001` MEDIUM `VERIFIED`
- New architect findings: 0
- Open CRITICAL/HIGH/MEDIUM issues: 0

## QA Audit

QA was sufficient. The HISTORIAN pass walked the required §5.5.7-§5.5.9
surfaces, compared native-loaded DuckDB with forced Python fallback, included
scoped dynamic unit arguments after the FP-08 SKEPTIC fix, and probed
singleton/error boundaries. No `RETRY_QA` flag is needed.

## Validation Reviewed

```bash
python3 .temp/qa/fp08_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_empty_quantity_unit_parity.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
python3 conformance/scripts/run_fhirpath_r4.py
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp08_historian_fresh_probe.py
```

Final full conformance: 2822/2822.

## Recommended Fix Order

No follow-up fixes are required for this inner loop. Remaining milestone review
items `REV-FP-002` and `REV-FP-003` remain outside this chunk unless a later
chunk intersects them directly.
