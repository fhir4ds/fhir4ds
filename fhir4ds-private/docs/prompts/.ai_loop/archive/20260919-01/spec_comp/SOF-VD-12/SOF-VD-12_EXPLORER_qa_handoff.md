# QA Handoff — SOF-VD-12 EXPLORER (3rd launch, iteration 1, 2026-08-24)

Personality: EXPLORER (boundary probing / adversarial metadata breadth).
Workspace: `.temp/qa/sof_vd12_explorer/` (probe.py 7/7 PASS, probe2.py 3/4 PASS —
E2 FAIL is the logged issue).

## Probed (all against /mnt/d/fhir4ds tree, PYTHONPATH=/mnt/d/fhir4ds)

- **P1 Canonical metadata round-trip at full breadth — PASS.** Every
  CanonicalResource/DomainResource field (publisher, publisherContact, contact
  with name+telecom+photo attachment data, useContext with valueCodeableConcept /
  valueQuantity / valueRange, identifier with assigner Reference, experimental,
  date (date AND dateTime shapes), approvalDate, lastReviewDate,
  effectivePeriod, purpose, copyright, copyrightLabel, language, text.div,
  contained resources, extension arrays with NESTED extension structures,
  modifierExtension, mapping with identity/uri/name/comment/commenti,
  implicitRules) round-trips verbatim through parse -> to_dict (deep equality
  per key). No coercion, no drops.
- **P2 meta breadth + versioned canonical enforcement — PASS.** meta retains
  versionId/lastUpdated/source/security/tag verbatim; meta.profile versioned
  canonical (`|1.0.0`) both enforces Tabular rules and round-trips verbatim.
  Profiled VD missing status rejected (pinned stance).
- **P3 Shareable+Tabular combined, nested unionAll — PASS.** A collection
  column inside select.unionAll triggers the Tabular no-collections error
  naming the column; a missing Column.type inside unionAll triggers the
  Shareable error naming the column. Both rules fire through
  _iter_select_columns recursion; error messages are clear (rule + column
  name). Constants coexist with profile enforcement.
- **P4 status/version/date shapes — PASS.** status restricted to the 4
  PublicationStatus codes; bad codes, wrong types, and explicit JSON null
  rejected. version accepts semantic-version strings verbatim. `date` (extra
  field) preserved verbatim for date and dateTime shapes.
- **P5 XML rejection quality — PASS.** XML with/without declaration,
  FHIR-namespaced, malformed pseudo-XML, and bytes input all rejected with
  clear typed ParseError ("XML ViewDefinition parsing is not supported...") or
  TypeError — no crashes, no silent acceptance.
- **P6 Official example byte fidelity — PASS.** All 5 official 2.0.0
  Binary-* examples: parse -> to_dict deep-equal to the original decoded
  payload (order/whitespace-insensitive), including the Shareable example.
- **P7 meta.profile canonical variants — PASS.** Versioned (`|0.1.0`),
  version+fragment (`|0.1.0#frag`), and fragment-suffixed canonicals: all
  enforce (version stripped for matching, fragment tolerated) and round-trip
  verbatim. Foreign canonicals ignored for enforcement + retained.
- **E1 End-to-end execution of Shareable+Tabular profiled VD — PASS.**
  Generates SQL (metadata never leaks into SQL), executes correctly on DuckDB
  with constants + forEach + where + union-free nesting: [('p1','Doe')].
  Native (C++ ext, allow_unsigned) vs Python-fallback outputs identical
  (PARITY: True).
- **E3 Adversarial metadata edges — PASS.** Non-string and null
  meta.profile entries rejected; empty-string canonical rejected (valid FHIR
  canonical is non-empty); top-level ViewDefinition.profile (resource-target
  profile, distinct from meta.profile) correctly does NOT trigger
  Shareable/Tabular enforcement and round-trips verbatim.
- **E4 mapping round-trip — PASS.** Full mapping objects incl. comment /
  commenti arrays retained verbatim; unknown-key permissiveness pinned.

## Findings

**QA-001 (MEDIUM, OPEN) — Constant decimal round-trip breaks JSON
serialization.** parse(JSON string) uses parse_float=Decimal; Constant.to_dict
emits the Decimal verbatim, so `json.dumps(vd.to_dict())` raises TypeError for
any VD with a valueDecimal constant. Dict-input keeps float, so to_dict's
output type depends on input path (Decimal vs float). Chunk mandate requires
JSON representation round-trip through parser inputs. Fix must preserve the
pinned Decimal losslessness doctrine (no float coercion) for FHIRPath literal
substitution.

## Environment notes
- duckdb 1.5.2; native fhirpath ext is unsigned dev build — use
  duckdb.connect(config={'allow_unsigned_extensions': True}) or fhir4ds.connect()
  for the native path.
- resourceType canonical form `https://sql-on-fhir.org/ig/StructureDefinition/ViewDefinition`
  required when present (probe authoring detail).
- where conditions: string OR {path, ...} object forms both accepted at top
  level; list items as bare strings rejected by parser (list of objects is the
  fixture form).

## NOT A BUG pins added
- Empty-string canonical in meta.profile rejected (FHIR canonical non-empty).
- Top-level ViewDefinition.profile ≠ meta.profile: never triggers profile
  enforcement.
