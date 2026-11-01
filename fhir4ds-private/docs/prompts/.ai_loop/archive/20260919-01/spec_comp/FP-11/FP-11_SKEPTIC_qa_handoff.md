# QA Handoff — FP-11 §5.7 Math (SKEPTIC), iteration 1

Probed ~85 dual-path (native extension vs forced Python fallback) cases via
`fhirpath_text` against /mnt/d/fhir4ds/.temp/qa/probe_fp11.py and probe2.py
(PYTHONPATH=/mnt/d/fhir4ds). Verified normative text against FHIRPath N1
2.0.0 §5.7 (spec/N1/index.adoc, HL7/FHIRPath repo) and current STU3
functions.json. Official fixtures (tests-fhir-r4.xml testAbs/Ceiling/Exp/Ln/
Log/Power/Round/Sqrt/Truncate) all pass already.

Confirmed clean: abs/ceiling/floor/truncate typing (Integer; Quantity keeps
unit), traditional round ties (0.5->1, -0.5->-1, 0.15.round(1)->0.2),
round precision guards (negative/non-integer/empty -> error/empty),
ln/log/sqrt domain empties, exp overflow empty, 0.power(0) empty, Quantity
rejection for ln/log/sqrt/exp/power, singleton enforcement, int32 abs
overflow empty.

Issues opened: QA-001 MEDIUM (power Integer typing, both engines),
QA-002 HIGH (native binary64 noise for Decimal-base power),
QA-003 MEDIUM (fallback round negative zero), QA-004 MEDIUM (fallback
power fractional-exponent 28-digit vs native shortest-round-trip),
QA-005 LOW INTENDED (round is traditional, not half-even; transcendental
binary64 shortest-round-trip rendering is pinned doctrine — launch brief's
half-even/28-digit hint superseded by normative text + existing pins).

Existing pin to update with QA-001 fix:
fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py:211-214
pins 2.power(3) as Decimal — contradicts normative Integer typing; no
documented rationale in AGENTS.md/GLOBAL_KNOWLEDGE.
