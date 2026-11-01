# S26 Slice 1 — Workspace/Zip Contract (inline design artifact)

Scope: items 10/11 mechanics only — the architecture was decided in
session (workspaces everywhere; zip == workspace, one source; replace
synthetic cms125; fixture-official expected values).

## 1. Fixture → workspace mapping

Source of truth per workspace:

| Workspace | Libraries | Valuesets | Measure | Patients |
|---|---|---|---|---|
| `demo-workspace` | existing `CleanroomDemo`-family CQL (hand-authored, stays) + ONE new valueset-using define | one small hand-authored ValueSet | existing demo Measure | existing 3-patient set |
| `cms125-workspace` (REAL, replaces synthetic) | `tests/data/ecqm-content-qicore-2025/bundles/mat/CMS125FHIR-R2-MeasureExport/cql/*.cql` (CMS125FHIRBreastCancerScreening-0.4.000 + include closure: FHIRHelpers 4.4.000, QICoreCommon, Status, Hospice, AdultOutpatientEncounters, AdvancedIllnessandFrailty, CumulativeMedicationDuration, PalliativeCare, SupplementalDataElements, AHAOverall) — CQL TEXT (not ELM JSON) | every `ValueSet/` resource in the MAT bundle JSON | `Measure-CMS125FHIRBreastCancerScreening.json` from the MAT bundle | the six DQM-2026 MADiE test cases (`tests/data/dqm-content-qicore-2026/input/tests/measure/BreastCancerScreeningDQMDraft/<Case>/`) — one `Patient/<case-id>/` folder per case (case's Patient + Encounter/Observation/Condition/Coverage resources), EXCLUDING the expected MeasureReport (that lives in `Measure/expected/`) |
| `cms69-workspace` (NEW) | `tests/data/ecqm-content-qicore-2025/bundles/measure/CMS69FHIRPCSBMIScreenAndFollowUp/...-files/CMS69FHIRPCSBMIScreenAndFollowUp.cql` + its include closure from the same tree | CMS69 valuesets from its bundle | CMS69 Measure resource | CMS69 test patients (from its MAT TestCaseExport if present, else the website example's dataset) |

Layout = canonical convention everywhere: `Library/<Name>.cql`,
`ValueSet/<id>.json`, `Measure/<id>.json`, `Measure/expected/<case-id>.json`
(fixture-official MeasureReports), `Patient/<case-id>/<Type>-<rid>.json`.
Legacy dirs are NOT created. `_attic/` holds the replaced synthetic
content (already the case for cms125).

## 2. Expected-results pinning (fixture-official)

- Expected per-patient MeasureReports are the DQM-2026 fixture
  `MeasureReport-*.json` files, copied VERBATIM into
  `Measure/expected/` (no recomputation, no reformatting).
- The cleanroom's Expected Results surface reads them from disk in
  connected mode (server route — slice 1 wires the reading path;
  authoring stays the existing UI).
- Population counts come from the fixture's `group.population.count`
  values — `initial-population/denominator/denominator-exclusion/numerator`
  per case. These are the (c)-agreed "fixture's official expected values".
- KNOWN HONEST GAP (documented, not hidden): the cms125 workspace ships
  the OFFICIAL CMS125FHIR v0.4.000 CQL (the MAT bundle text). The
  fixture cases were authored against the DQM-2026 DRAFT library whose
  numerator adds "Mammography Claim"/"Mammography EOB" paths (needs
  FHIRCommon/USCoreCommon/C4BB libraries absent from the repo). With
  the official v0.4.000 text, 4/6 cases MATCH their fixture-official
  pins; BCSNumeratorClaimPass/EOBPass mismatch in the numerator only
  (expected: pass; official logic reads ObservationClinicalResult
  only). The compare surface shows this truthfully.
- Measurement period for fixture pins: 2026-01-01..2026-12-31 (each
  fixture MR's own `period`).
- MADiE cases share resource ids ACROSS cases (designed for
  one-case-per-kernel); the generator namespaces non-Patient ids per
  case (`sha1(case)[:8]-<rid>`, ≤64 chars, FHIR-charset-valid) and
  rewrites all References so all cases coexist in ONE kernel.

## 3. Zip layout (item 11 — built in slice 2, contract fixed here)

- A workspace autozip is the MADiE-style package over the SAME content:
  `library/<Name>.cql` (lowercase plural dirs per MADiE), `valueset/*.json`,
  `measure/<Measure>.json`, plus `tests/<case-id>/{Patient-*.json, ...resources}`
  — the existing MADiE loader grammar.
- The generator emits BOTH shapes from one in-memory model; the zip is
  never hand-edited.
- Compatibility gate: the zip loads through the EXISTING
  `parseMadiePackage` (src/lib/madiePackage.ts) with no loader change
  REQUIRED.

## 4. Invariants

- Generator is IDEMPOTENT + reproducible (sorted file emission, stable
  JSON serialization); running it twice produces identical trees.
- No fixture mutation: the generator only READS tests/data; it writes
  exclusively under `examples/`.
- Version metadata inside libraries/valuesets is copied verbatim from
  the fixture (CMS125FHIR v0.4.000 etc.).
- devserver `_workspace_roots` already lists `examples/*-workspace` —
  no server change needed for the picker.
