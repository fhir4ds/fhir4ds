# QA Handoff — FP-15 EXPLORER (2026-08-18)

Personality: EXPLORER. 121-case dual-path probe + 2 drills (`.temp/qa/fp15_explorer2_2026_08_18/`).
Coverage per chunk mandate: all FHIR primitives across real fields, is/as chains
(as->DomainResource->Resource), is/as feeding where/select/repeat/iif, System.* vs
FHIR.* spellings, Quantity subtypes on real fields, multi-type contained, multi-item
focuses, deep nesting both syntactic forms, defineVariable (rejected by pattern check
on BOTH engines — pre-existing, not §6.3).

## Findings
- QA-001 HIGH — native infix is/as CHAIN bug: parser.cpp parseTypeExpression parses at
  most one `('is'|'as') typeSpecifier`. `Patient as Resource is FHIR.Patient` -> EMPTY
  native vs true fallback. Official FHIRPath.g4 typeExpression rule is left-recursive
  (`expression ('is'|'as') typeSpecifier`), chains are valid. Spec: §6.3 + grammar.
- QA-002 MEDIUM — `recorded` (AuditEvent/Provenance) typed string on both engines;
  R4 says instant. `recorded is FHIR.instant` false both.
- QA-003 MEDIUM — `meta.lastUpdated` typed dateTime natively (wrong per R4: instant)
  AND a native/fallback parity diff (fallback infers neither dateTime nor instant).
- QA-004 LOW — per-path-correct types unreachable: ValueSet.url canonical,
  note.text markdown, Claim.total Money, Encounter.length Duration, Narrative.div
  xhtml — all false on both engines. Native fhirFieldType is name-only; parity blocks
  fallback-only correction. REV-002/ARCH-002 family.

## Clean areas (verified, no issue)
All E1 primitive checks where metadata exists, E2 function-form chains, E3/E4 feeding
navigation/where/select/repeat/iif, E5 namespace spellings (incl. correct false for
System.* on FHIR values), E6 quantity subtypes false-consistent (metadata not
reachable; same class as QA-004 for fields), E7 contained multi-type, E8 multi-item
focus empty per §6.3 singleton rule, E9 deep nesting (parenthesized), exact-match `as`
doctrine for primitives unchanged.

Probe-artifact notes: `div` is a reserved word (integer division) — must backtick;
`(gender | id) is FHIR.string` empty is CORRECT (multi-item focus).
