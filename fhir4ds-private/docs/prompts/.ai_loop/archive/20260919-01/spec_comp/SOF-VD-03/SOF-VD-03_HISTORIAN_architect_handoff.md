# Architect Handoff — SOF-VD-03 (Select key elements), iteration 1, HISTORIAN

## Golden Standard (chunk-scoped invariants)
1. Select semantics must match processing_model.md's Cartesian-parts algorithm, not SQL intuition (empty part ⇒ zero rows; unionAll evaluated per focus, ordered last).
2. All cardinality/invariant violations must surface as an error before or at execution (parse-time vs generation-time is implementation latitude per prior SKEPTIC doctrine).
3. Column evaluation must ride the single fhirpath UDF surface (native or Python fallback, identical results).
4. The authoritative fixture source is the sql-on-fhir.js snapshot, not the IG clone's /tests directory.

## Audit summary
- QA quality: HIGH. The HISTORIAN pass tested axes the SKEPTIC pass missed: processing-model
  empty-part row suppression (P1/P2), unionAll-per-focus evaluation (P4), unionAll-only and
  bare selects (P3/P6), FHIRPath `|` de-duplication semantics for guard probes, strict-mode
  collection adjudication (opt-in profile, spec-exact default), native-vs-fallback parity at
  both UDF and full-view level, and fixture provenance of the IG clone's /tests (stale draft
  format — 60 raw divergences all adjudicated as artifacts). No QA veto.
- Structural spot-check: duplicate-column-name validation exists in BOTH parser.py
  (_effective_output_names) and generator.py (_collect_select_output_schema mirror). Their
  coverage differs slightly (parent-vs-unionAll-branch duplicates detected at generation,
  not parse), but every duplicate shape raises before execution — spec requires only an
  error. Noted as a drift-risk observation; no action this launch (consistent behavior today).
- No silent fallbacks, no test-driven hacks, no hardcoded model knowledge observed in the
  select code paths audited this launch.

## Issues (final state)
- QA-001 LOW DEFERRED (carried): conflated runtime guard message; error raised, spec satisfied.
- QA-002 LOW INTENDED: IG clone /tests = stale draft fixtures; AGENTS.md note added.

## Compression
QA (HISTORIAN, iter 1): ~35 new probes across parser/generator/execution both engines; zero
CRITICAL/HIGH/MEDIUM; SKEPTIC's preflight-warning fix re-verified. Engineer: no code changes
needed; gates fresh on final tree — viewdef pytest 1171/1171, ViewDef 144/144, master
2832/2832; fhirpath binary md5 57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages.

## Exit
Clean exit at iteration 1 (>= min_iterations 1, zero non-terminal CRITICAL/HIGH/MEDIUM).
Recommended for future launches on this chunk: none mandatory; optional LOW polish is
splitting the runtime guard message (needs suite unpinning).
