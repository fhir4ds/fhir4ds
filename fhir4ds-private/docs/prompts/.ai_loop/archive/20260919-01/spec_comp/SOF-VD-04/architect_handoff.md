# Architect Handoff — SOF-VD-04 (HISTORIAN), iteration 1

Golden standard: /mnt/d/fhir4ds/.temp/architect/golden_standard.md (7 invariants, reused
from the SKEPTIC launch — still accurate for this chunk).

## Audit of this launch's change (single fix, generator.py)
- QA-001 fix (`_is_element_id_type` colon exclusion): class-based, not input-specific;
  single classification site consumed by `_get_udf_for_type`,
  `_is_complex_declared_type`, and `_validate_element_id_column_types` (invariants 2, 7);
  no hardcoded FHIR names (3); generation-side, engine-agnostic (4); keeps failing fast
  with a typed, actionable ValidationError — no silent fallback (5).
- QA-002 confirmed INTENDED per the documented portable runtime-guard doctrine; recorded
  in the viewdef AGENTS.md NOT A BUG registry.

## QA Enforcer Gate
HISTORIAN QA was thorough: fetched the canonical v2 2.0.0 StructureDefinition from the
HL7/sql-on-fhir releases branch (noting the live CI build now serves v3.0.0-ballot —
valuable environment discovery), walked every normative column sentence (sql-name,
duplicate names, collection default/SHALL-guard, type URI semantics, tag 0..*/1..1s),
probed NEW angles beyond the SKEPTIC pass (complex collection types, full-URI primitives,
numeric widening, code-vs-string, complex-under-primitive guards, mixed unions, URI edge
cases), re-verified both SKEPTIC fixes regression-free, and parity-checked native vs
Python fallback on every executed case. No veto. RETRY_QA stays false.

## Compression
QA (HISTORIAN) found zero CRITICAL/HIGH/MEDIUM and two LOWs: (1) dotted absolute URIs
misdiagnosed as element-ID types with a misleading cross-resource error — fixed
surgically in generator.py with a focused regression test; (2) same-resource element-ID
misdeclaration unreported — INTENDED per doctrine. Validation on the final tree:
ViewDef pytest 1178/1178, master gate 2832/2832, binaries untouched and md5-matched
(repo==site-packages).

## Recommended Fix Order
None — no open issues.
