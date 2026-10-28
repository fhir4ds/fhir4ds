# DESIGN: OMOP CDM v5.5 Mapping via ViewDefinitions (fhir4ds side)

Status: DESIGN FOR JOEL + MUSE GATE — branch feat/omop-v55-mapping
Mission: FHIR R4 → OMOP CDM v5.5 tables as a ViewDefinition library,
architecture LOCKED by Joel (concept-map runtime join; FHIR-native chain).

## 0. Locked architecture (Joel 2026-10-23, presented as decided)

```
Athena CONCEPT table
  └─ (converter — medterm4ds side or shared tool) ─▶ FHIR ConceptMap RESOURCE
        one group per source vocabulary: source=FHIR system URI, elements
        {code, target.code=concept_id-as-string, target.equivalence}
  └─ ConceptMap VIEW: a VD over the ConceptMap resource (conceptmaps table)
        → long/thin mapping rows: vocabulary_id | concept_code | concept_id
  └─ per-OMOP-table VDs JOIN the ConceptMap view (native VD `joins`)
        join keys: source vocabulary_id + concept_code (Joel-locked)
```

- Runtime join is the ONLY core mechanism. Compile-time %Constant/CASE
  baking: NOT core (at most a demo nicety; dropped from scope).
- Live `%translate()` service calls: REJECTED for VDs (couples execution
  to a service; that is the CQL layer's answer).
- Everything is FHIR-native resources + VDs end to end.

## 1. ENGINE PREREQUISITE GAP (found by live probe, must be S0)

The VD spec's root-level `joins` PARSE and validate in fhir4ds today but
the SQL generator NEVER EMITS them — `JoinGenerator` exists
(fhir4ds/viewdef/join.py:171, unit-tested in isolation at
tests/unit/test_join.py) and is wired NOWHERE; the integration test at
tests/integration/test_duckdb.py:2705 documents the gap in its own
comment ("Current SQL generator generates basic patient query").
Verified live: a VD with `joins:[{name: cm, resource: ConceptMap, ...}]`
generates SQL with no JOIN clause and join-aliased paths resolve empty.

**S0 (new slice, before any mapping): emit root joins in
SQLGenerator.generate()** — table name resolution must honor the
generator's `source_table` mode (shared `__vd_src` staging joins by
resourceType, exactly how the base FROM works) so the Viewing Room and
notebooks can run join VDs unchanged. Includes: ON-clause FHIRPath
evaluation over the joined resource, join-alias path resolution in
column paths (e.g. `cm.group.element.target.code`), integration tests,
and the spec-grammar parity questions (see §7 open questions).

## 2. Scope matrix — mined from OMOP-on-FHIR v5.4-R4 (their coverage first)

Their mapper inventory (omoponfhir-omopv5-r4-mapping/src/main/java/
edu/gatech/chai/omoponfhir/omopv5/r4/mapping/): per-table starting
mappings with file citations; v5.5 DDL facts from the official cdm55
page; gaps marked FRESH where neither they nor we have provenance.

| OMOP v5.5 table | FHIR source(s) | Their file | Their decisions adopted | v5.5 delta / FRESH notes |
|---|---|---|---|---|
| person | Patient | OmopPatient.java | person_source_value=Patient.id; gender via Gender-domain concepts (their FhirOmopCodeMap); year/month/day + birth_datetime from birthDate | FRESH: race/ethnicity from us-core-race/ethnicity extensions → Observation fallback per CDM convention; gender_concept_id via ConceptMap join (Gender domain; administrative-gender is NOT a standard vocab — mapping rows must be authored, see §3) |
| observation_period | Encounter (derived) | (none — they never populate ObservationPeriod; verified: zero ObservationPeriod references) | — | FRESH: min(first event start) .. max(last event end) per person is an AGGREGATE, not a row mapping — out of scope for pure VDs; v1 ships visit-grain rows as observation_period candidates + documented ETL note (THEMIS: EHR periods are ETL-defined) |
| visit_occurrence | Encounter | OmopEncounter.java | class → visit_concept_id (IMP→9201, AMB→9202, EMER→9203 via v3ActCode); visit_source_value=class code; period.start/end | FRESH: type_concept_id=32810 (EHR encounter) default; provider/care_site remain 0 (FHIR weakly carries them via practitioner/org refs — deferred, see §5) |
| condition_occurrence | Condition | OmopCondition.java | code→condition_concept_id; category→type_concept_id (problem-list-item→38000245, encounter-diagnosis→43542353; else 0 — OmopConceptMapping.java:76-79); onset[x]→start; abatement→end; encounter→visit_occurrence_id | v5.5: no change vs 5.4 fields. condition_status from clinicalStatus |
| drug_exposure | **UNION**: MedicationRequest + MedicationStatement + MedicationAdministration + Immunization | OmopMedicationRequest.java, OmopMedicationStatement.java, OmopImmunization.java | each maps to DrugExposure; Immunization→drug (vaccine concept); quantity/daysSupply from dosage; type provenance per source | FRESH: consistent union pattern (§4); MedicationAdministration added (their v5.4 code lacks it — only Request/Statement/Immunization exist); drug_type_concept_id per-branch (prescription-written vs dispensed vs administered per CDM) |
| procedure_occurrence | Procedure | OmopProcedure.java | code→procedure_concept_id; performed[x]→procedure_date; performer→provider | quantity defaults 1 per CDM when absent |
| device_exposure | **UNION**: DeviceUseStatement (+ DeviceRequest?) | OmopDeviceUseStatement.java | code→device_concept_id; UDI parsing for unique_device_id | DeviceRequest deferred (their code lacks it); quantity default 1 |
| measurement | Observation (lab + Quantity-valued) | OmopObservation.java:1380-1440 | **isMeasurementByValuetype: value[x] instanceof Quantity → Measurement**; else domain-check (concept domain 'Measurement' + vocabulary match); BP component split (systolic/diastolic, handleBloodPressure :456) | FRESH: we generalize their Quantity-rule as the PRIMARY discriminator (pure FHIRPath, no Athena domain lookup needed at split time); referenceRange.low/high→range_low/high; unit via UCUM→unit_source_value |
| observation | Observation (non-lab: Ratio/coded/string/date-valued) | OmopObservation.java | isObservationByValueType: Ratio→Observation; else falls to observation | FRESH: value_as_string/date handling per v5.5 fields (value_as_date is NEW in 5.5) |
| death | Patient.deceased[x] (+ Observation death certs FRESH) | OmopPatient.java (TODO :85 "death: need to revisit"; never implemented) | — | FRESH: deceasedDateTime→death_date; cause from Condition/observation code where linked; type_concept_id default 32810-ish provenance |
| note | DocumentReference / Composition | OmopDocumentReference.java | exists in their tree | DEFERRED to v1.1 (notes NLP surface is large; not in the spine Joel listed) |
| specimen | Specimen | OmopSpecimen.java | exists | DEFERRED to v1.1 (v5.5 only added visit FKs) |

Out of scope v1: payer_plan_period, cost, eras (derived), episode,
cohort, visit_detail (FHIR has no clean detail grain), provider/
care_site/location as TARGET tables (see §5).

## 3. Concept-id strategy — the chain, concretely

**Default concept_id = 0** everywhere the join misses (valid OMOP;
source codes preserved). The ConceptMap resource carries the lift:

- Converter (medterm4ds or shared tool; NOT this campaign's code):
  Athena CONCEPT rows → ConceptMap groups. `group.source` = the FHIR
  system URI, `group.target` = `urn:omop:concept` (custom), element.code
  = concept_code, target[0].code = String(concept_id).
- ConceptMap VD (ours): `resource: ConceptMap`, `repeat` over
  group.element.target; columns vocabulary_id (derived from
  group.source via a system→vocabulary_id constant table IN THE VD's
  constants — small, closed set, §caveat), concept_code, concept_id,
  concept_name (target.display), domain_id (needs converter-side
  pass-through: target.extension or a second group field — open
  question Q2).
- OMOP VDs join it: ON (source vocabulary_id, concept_code) equality,
  LEFT JOIN, COALESCE(concept_id, 0).

Caveat handled as design decision: the FHIR-system→OMOP-vocabulary_id
table (LOINC→LOINC, SNOMED→SNOMED, ICD-10-CM→ICD10CM, RxNorm→RxNorm,
CPT4, HCPCS, NDC — exactly OmopCodeableConceptMapping.java:30-43's set,
adopted) is a CLOSED, small, stable mapping → ships as VD `constant`
sets (compile-time data, not concept mappings — does not violate the
constants-rejected ruling; it is vocabulary metadata, not codes).

Fresh-authored mapping rows required at v1 (no Athena vocab covers
these; small curated ConceptMap supplements): administrative-gender →
Gender domain (8532/8507/0), v3ActCode encounter classes → Visit
(9201/9202/9203 — OmopConceptMapping.java:68-71 values adopted),
condition category → Type Concept (38000245/43542353/0 — :76-79
adopted), type_concept_id provenance defaults (32810 EHR-era set).

## 4. Union pattern (Joel-locked, designed once)

Per multi-source OMOP table: N resource-specific CHILD VDs (one per
FHIR resource, full table columns, source-tagged) → one table-level
UNION VD. Mechanism: the SQL-on-FHIR `unionAll` in select branches
cannot span resource types (one VD = one resource root), so the union
is a VD LIBRARY convention: each child VD is generated/executed
separately and UNION ALL'd by the runner (viewdef runner composing
named views — `CREATE VIEW omop.drug_exposure AS SELECT ... UNION
ALL ...`); a thin composition doc per table. Applies to:
drug_exposure (4 sources), device_exposure (1 now, 2 later),
observation+measurement (same source, DISJOINT by value-type rule —
two VDs over Observation with mutually exclusive `where` clauses, not
a union), death (2 sources).

## 5. Feasibility: required-but-weak fields (documented policy)

- type_concept_id (required in EVERY event table): FHIR carries no
  provenance of this shape → constant default 32810-family per table
  with per-source overrides (their category mapping adopted for
  condition; their encounter-class mapping for visit). Documented as
  the ETL assumption.
- provider_id / care_site_id: FHIR has practitioner/organization
  references but no stable integer ids; v1 emits the reference string
  in provider-source-adjacent columns and 0 in the FK columns
  (valid OMOP; documented).
- person_id/visit_occurrence_id integer grain: FHIR ids are strings.
  v1 emits `person_id` as the Patient id STRING in a typed
  `person_source_value`-like column AND a deterministic integer hash
  where the DDL demands integer (xxhash64 modulo 2^31; documented,
  stable, collision-risk noted). Same for visit_occurrence_id
  (Encounter id hash) and *_occurrence_id PKs (resource id hash).
- *_datetime vs date: FHIR dateTime carries both; date columns take
  substring(0,10), datetime columns the full value (DuckDB VARCHAR
  transport per the fixtures-pin doctrine).

## 6. Sample + demo

Synthetic bundle (hand-authored, ~6 patients × spine resources with
LOINC/SNOMED/ICD10/RxNorm codings + the 25-patient reference set where
codes permit): runnable BOTH as (a) a Viewing Room sample pack
(`omop-cdm-55` gallery entries — one per OMOP table view; the
playground becomes the OMOP demo surface, per Joel's synergy note) and
(b) `docs/notebooks/omop-mapping.ipynb` (build views over staged NDJSON,
show resulting OMOP-shaped tables). Expected-row validation: a fixture
JSON asserting per-table row counts + spot cell values (concept_id
resolution, date splits, 0-defaults).

## 7. Test strategy (spec-comp doctrine, sectioned suite)

`fhir4ds/viewdef/tests/omop/` (new section family, run with the
conformance gate):
- **Schema section**: per-table DDL asserts — exact column-name set +
  order vs a parsed CDM 5.5 DDL fixture; type shape (integer vs
  varchar vs date columns typed in the VD).
- **Required-field section**: non-null asserts on every required=true
  column (given the demo bundle) + the 0/defaults policy.
- **Grain section**: one-row-per-expected-resource (and per
  component for BP measurement split), union counts = sum of children.
- **Mapping section**: concept resolution through the ConceptMap join
  (hits→concept_id, misses→0), the value-type measurement/observation
  split, date/datetime duals, hash stability (same id → same integer).
- **VD-conformance**: every library VD parses + generates + executes
  against the sample bundle (the §6 fixture doubles as the corpus).

## 8. Versioning

Library artifact `omop_v55/` under `fhir4ds/viewdef/resources/omop/`
(one JSON VD per child view + manifest {omop_version: "5.5", fhir4ds
min version, conceptmap resource, vocabulary constants, union
composition docs}). v5.4 delta is SMALL (7 optional fields added, 3
vocab metadata tables — none in our spine scope; verified from
cdm55Changes) → a `omop_v54` variant is a manifest flag dropping
value_as_date/unit_source_concept_id/value_as_source_concept_id from
observation/measurement; designed, not shipped v1.

## 9. Slices (S0 bounded per Muse R3)

- **S0**: engine — root-joins SQL emission (§1) + integration tests
- **S1**: concept chain — ConceptMap VD + vocabulary constants +
  curated supplements (§3) + tests
- **S2**: spine tables — person, visit_occurrence, condition_occurrence,
  procedure_occurrence (single-source tables, §2 rows 1-4,7) + tests
- **S3**: unions + split — drug_exposure (4-way), device_exposure,
  measurement/observation value-type split, death (§2 rows 5-6,8-10) +
  tests
- **S4**: demo — sample bundle + Viewing Room sample pack + notebook +
  expected-row fixtures (§6)
- **S5**: conformance wiring — sectioned suite into the gate (§7),
  versioning manifest (§8), docs

## 10. Muse gate verdict + folded recommendations

Verdict: **SHIP-WITH-CHANGES** (Muse endpoint down; gemini fallback
used as the independent reviewer). Seven recs, all folded:

- R1 → §3: ConceptMap VD filters `target.equivalence in
  ('equivalent','equal')` and takes `first()` — strict
  (vocabulary_id, concept_code) → concept_id functional dependency
  before any event join; multi-target maps CANNOT fan out rows.
- R2 → §3: explicit coding-selection precedence in every event VD:
  unnest codings, LEFT JOIN conceptmap per coding with the
  standard-vocab priority (SNOMED/RxNorm/LOINC > ICD10* > local),
  pick the highest-priority RESOLVED concept, else the first coding's
  source value (never `coding.first()` blindly, never row fan-out).
- R3 → §1/S0: S0 bounded to root-level LEFT JOIN + equality of scalar
  projected paths + source_table staging resolution. Non-equi joins
  and arbitrary ON-FHIRPath predicates explicitly deferred.
- R4 → §5: hash policy upgraded to POSITIVE 63-BIT integers
  (`xxhash64 & 0x7FFFFFFFFFFFFFFF`) for person/visit/PK columns —
  collision-safe at any realistic scale (mod-2^31 rejected: ~1%
  collision at 6.5k entities).
- R5 → §7: grain section gains multi-coded-resource cardinality
  preservation (resource count == mapped row count through joins) and
  referential-integrity asserts (every event.person_id resolves in
  person).
- R6 → §4/S4: the union composition ships as a real runner artifact
  (`CREATE VIEW omop.<table> AS ... UNION ALL ...` over child VD SQL)
  + the Viewing Room sample pack surfaces the composed tables.
- R7 → §2 measurement/observation split: Quantity-rule primary;
  documented trade-off — qualitative labs (valueCodeableConcept) land
  in observation by the value-type rule; secondary category
  ('laboratory') fallback considered and deferred to v1.1 (their
  domain-based logic required Athena at split time; ours stays
  FHIRPath-pure; documented as the known divergence).

## 11. Open questions for Joel (non-blocking, S0-S1 answers shape S2+)

- Q1: S0 joins emission is ENGINE work beyond pure VD authoring —
  confirm it belongs in this campaign (recommend YES: nothing else in
  the locked architecture is buildable without it).
- Q2: domain_id pass-through — converter includes CONCEPT.domain_id in
  the ConceptMap (target.extension) OR we omit domain_id from the
  ConceptMap view v1 (their domain-based split is replaced by the
  value-type rule anyway; recommend omit v1).
- Q3: person_id hashing policy — xxhash64-as-integer (recommend) vs
  emit string-only and leave integer FK columns 0 everywhere.


## Implementation record (S0-S5, 2026-10-23)

All slices landed on feat/omop-v55-mapping; every acceptance item of the
design maps to shipped artifacts:

- S0 (7696b13b): root joins emitted (LEFT/INNER/RIGHT/FULL; equality-pair
  ON; source_table staging via derived subquery; join-prefixed column and
  where routing; guard rails). 10-test integration suite.
- S1 (2220db86): conceptmap-view.json + curated supplements (NDJSON
  element-per-resource) + vocabulary.json. Muse-R1 functional dependency
  via target.where(...).first().
- S2 (061dd306): person / visit_occurrence / condition_occurrence /
  procedure_occurrence with Muse-R2 coding precedence + system-discriminated
  ON pairs.
- S3 (bb392829): drug_exposure 4 arms (canonical 14-column set),
  device_exposure (DeviceUsage — R6 rename), measurement/observation
  value-type split, death.
- S4 (35fe98b1): omop_runner.create_omop_views — omop.* schema, unions,
  positive 63-bit key projection, concept-0 defaults; demo bundle +
  expected-rows fixture; Viewing Room omop-patient + omop-drug-exposure
  gallery samples (14/14 e2e); omop-mapping.ipynb executed clean from the
  built wheel.
- S5 (this commit): manifest.json (versioned artifact + ETL assumptions +
  v5.4 variant note) + sectioned conformance suite
  (conformance/scripts/run_omop.py: schema/required/grain/mapping/
  vd-conformance) wired into run_all — MASTER GATE 2869/2869 (100%).

Key implementation findings (beyond the design):
- The join target for concept resolution is the ConceptMap in
  ELEMENT-PER-RESOURCE form (one thin ConceptMap per mapping row): the S0
  scalar-equality ON cannot select a nested element inside a monolithic
  ConceptMap. The converter contract (medterm4ds side) emits that form.
- DeviceUseStatement was renamed DeviceUsage in the current metadata
  binding (R6); the device view targets DeviceUsage.
- OMOP_DIR path bug + report-shape alignment fixed during S5 wiring.

Deferred (documented, out of v1): observation_period (ETL-defined
aggregate per THEMIS), note/specimen tables, DeviceRequest arm,
race/ethnicity Observation fallback, provider/care-site integer FKs
(0 + reference strings), v5.4 manifest variant.

---

# REVISION 2 (2026-10-24): View-as-join-target — the thin-form workaround REMOVED

Status: REVISED DESIGN FOR JOEL — pre-implementation review
Trigger: Joel's reconsideration ruling + spec confirmation (cbus
2026-10-24 09:58 / 10:03). Supersedes the "architecture finding" in the
S2 record and §0's converter-contract implication.

## R.0 The ruling and why it is correct

Joel: "we need to be able to join on nested elements. we are able to do
this WITHIN a ViewDefinition [select/forEach reaches nested elements
fine]. not sure why we can't do it in a JOIN to one. this seems like we
have just structured the ViewDefinitions incorrectly."

The S2 "engine constraint" analysis was wrong about the fix. True fact:
the S0 scalar-equality ON cannot select a nested element inside a
monolithic ConceptMap resource (an ON path like
`group.element.code` evaluates the FIRST element only). Wrong
conclusion: "therefore the converter emits one thin ConceptMap per
mapping row." Correct conclusion: the JOIN TARGET should be the
FLATTENED VIEW — the `omop_conceptmap` ViewDefinition (S1) already
unnests group/element/target via forEach into one row per mapping; the
join must compose with THAT, exactly as select/forEach composes within
a VD. The flattening machinery always existed; the S0 join just never
targeted a view's output.

## R.1 Spec citations (verified against the local IG clone,
/mnt/d/sql-on-fhir-v2, input/pagecontent + input/fsh)

1. ViewDefinition-notes.md (Joins with Resource and Reference Keys):
   "While ViewDefinitions do not directly implement joins across
   resources, the views produced should be easily joined by the
   database or analytic tools of the user's choice." — joins live in
   the COMPOSITION layer; the fhir4ds `joins` field remains a
   documented fhir4ds extension (types.py Join docstring), now aligned
   with that layer's semantics.
2. SQLView-notes.md (Query Composition): "References made through
   relatedArtifact form a directed graph of ViewDefinitions, SQLViews,
   and SQLQueries, in which **each referenced result acts as a virtual
   table for the referencing query**." and "The executing engine **may
   materialise the view's result or inline it**; either approach
   conforms to this specification." — view-as-join-target is the
   spec's composition semantics; materialization strategy is an
   implementation decision.
3. SQLQuery-notes.md: "An SQLQuery may reference a reusable SQLView as
   well as ViewDefinitions, letting queries build on one another much
   like SQL views." with `JOIN bp ON patient.id = bp.patient_id` in the
   worked example — joining to a view's OUTPUT COLUMNS is the
   spec-native pattern.
4. input/fsh/examples/sql-query-examples.fsh `OmopFhirPatientJoin`: the
   spec's own example joins an `omop_person` view to a FHIR patient
   view — an OMOP mapping joined at the view layer is precedent IN the
   spec.

## R.2 Revised architecture (supersedes the S2 finding)

```
Athena CONCEPT -> STANDARD MONOLITHIC ConceptMap resource (converter contract —
                  no bespoke form; FHIR-native, inspectable, portable)
      |
      v  (S1 omop_conceptmap VD: forEach unnests group/element/target —
      |   one row per (vocabulary_id, concept_code, concept_id), Muse-R1
      |   equivalence filter + first-target determinism)
      v
  FLATTENED CONCEPTMAP VIEW  (materialized by the runner as
      |                       omop.conceptmap or inlined as a CTE —
      |                       spec: "may materialise... or inline it")
      v
  per-OMOP-table event VDs JOIN THE VIEW via the extended fhir4ds
  joins construct (Join.view), ON (event best-coding = view
  concept_code) AND (event derived vocabulary_id = view vocabulary_id)
```

- The element-per-resource NDJSON supplements (S1) are REPLACED by the
  standard monolithic ConceptMap (one resource, three groups, as first
  authored). The thin form is reclassified as a POSSIBLE FUTURE
  OPTIMIZATION (pre-split rows for very large maps), never a contract.
- The medterm4ds converter (via conductor) reverts to emitting the
  monolithic ConceptMap only.

## R.3 Join.view — the engine extension (S6 slice)

Extend the fhir4ds `joins` extension with a VIEW target alongside the
resource target:

```json
{"name": "cm", "view": "omop_conceptmap", "type": "left",
 "on": [{"path": "<event FHIRPath>"}, {"path": "cm.concept_code"}, ...]}
```

Semantics (mirroring the spec's virtual-table language):
- `Join.view` names a ViewDefinition (by VD `name`; manifest-scoped).
  The runner materializes it first (CREATE VIEW over the staging
  table) — or the generator inlines it as a CTE; both conform.
- Join-target SHAPE determines path semantics: RESOURCE target → ON and
  column paths are FHIRPath over the joined resource JSON (unchanged
  S0); VIEW target → `<alias>.<name>` paths are SQL COLUMN REFERENCES
  into the view's output (`"cm"."concept_id"`), because a view's rows
  are already flat — FHIRPath over a row would be meaningless. The
  base-side ON expressions remain FHIRPath over the base resource.
- ON pairing and join keywords unchanged (equality pairs, S0 bounds).
- Validation: view target must not collide with the base alias; the
  referenced VD must exist in the library manifest (generate-time
  check); the referenced column names must exist in the view's output
  (execution-time, via the materialized view).

Generator changes (S6):
1. parser/types: `Join.view` (optional, mutually exclusive with
   `Join.resource`).
2. `_generate_single_resource`: view-target joins emit
   `LEFT JOIN omop.<viewname> "cm"` (runner-materialized) — the
   generator takes a `view_table_prefix` (default `omop`) or an
   explicit alias→table map from the runner.
3. `_route_join_path`: view-target routes emit column refs, not
   FHIRPath: `"cm".concept_id` → `"cm"."concept_id"` (identifier-
   quoted, no UDF call). Same for ON right-sides.

Runner changes: `create_omop_views` materializes
`omop.conceptmap` (the S1 VD SQL) BEFORE generating event VDs, and
passes the view-table mapping to the generator.

## R.4 Migration of shipped artifacts (S6 implementation scope)

- conceptmap-supplements: monolithic form (single ConceptMap, three
  groups) as the shipped artifact; delete the NDJSON thin form.
- Event VDs (person/visit/condition/procedure/drug×4/measurement/
  observation): `joins` entries become view-targets; concept columns
  become `cm.concept_id` (column ref); ON pairs become
  (best-coding ↔ cm.concept_code) AND (derived vocabulary_id ↔
  cm.vocabulary_id). The event-side vocabulary derivation uses the
  same system→vocabulary constants the conceptmap view uses (single
  source of truth: vocabulary.json).
- device_exposure / death: no joins (unchanged).
- omop_runner: materialize omop.conceptmap first; wire the generator's
  view-table map.
- Tests: test_root_joins gains a view-target section; test_conceptmap/
  test_spine_views/test_split_views/test_composite switch to the
  monolithic fixture; run_omop conformance unchanged in shape (it
  asserts the composed schema, which does not change).
- Demo bundle + Viewing Room samples + notebook: stage the monolithic
  ConceptMap.

## R.5 What does NOT change

Everything else stands: the spine field mappings (S2), the 4-arm drug
union + value-type split + death (S3), the composite runner's union
and 63-bit key projection (S4), the manifest/conformance shape (S5),
and the concept chain's vocabulary constants + curated supplement
VALUES. The S0 resource-target join semantics remain valid for
resource-to-resource joins (e.g. Observation→Patient).

## R.6 Slice plan

- S6a: engine — Join.view (parser + generator column-ref routing +
  runner view-table map) + view-target tests.
- S6b: library migration — monolithic supplements, event VDs to view
  joins, runner order, demo/samples/notebook fixtures.
- S6c: full regression — OMOP suite, master gate, viewing-room e2e,
  notebook re-execution.

Open question for Joel (non-blocking): CTE-inlining vs runner
materialization as the DEFAULT (recommend runner materialization —
matches the shipped omop_runner and the spec's "either conforms";
CTE-inlining stays available for single-query use).


## Sample data & scale findings (2026-10-26, Joel review follow-up)

Decision chain (Joel): the OMOP samples must use real, license-clean,
small data — conditions dropped (SNOMED/UMLS encumbrance), medications on
RxNorm (NLM public domain, self-mapping), data hosted on Hugging Face
rather than committed to git.

- **Dataset**: `fhir4ds/omop-demo` (public, CORS-enabled) — a 25-patient
  Synthea 4.0.0 R4 cohort (seed 20261026; MIT) plus the RxNorm ConceptMap
  subset. Browser fetch works directly (`/resolve/main/...`).
- **Two data tiers**: HF bundles are the production default
  (`OMOP_DATA_BASE` in samples.ts); committed compact fixtures (8-patient
  slice + 36-code map) serve `?data=local`, which the e2e suite uses so
  tests stay offline/fast. Network smoke test (`journey-remote.spec.ts`)
  exercises the HF path and skips when the dataset is unreachable.
- **DuckDB scale limit (verified, desktop + WASM)**: a monolithic
  ConceptMap with 157k elements cannot be unnested — DuckDB exhausts
  memory (`json_each`/`UNNEST` over huge JSON arrays; 50 GiB peak before
  OOM). Transport therefore chunks the map: one thin ConceptMap resource
  per 20 elements (3,573 resources for 71,444 concepts), flatten 2.4 s
  desktop / ~10-25 s WASM. Chunk size tunes per-row parse cost.
- **Subset choice**: RxNorm standard classes Ingredient + Clinical Drug +
  Branded Drug (71,444) → ~90% of the cohort's medication requests
  resolve; the remainder surface concept_id 0 with source values (the
  OMOP no-map convention, demonstrated by real data). Quant*/Pack
  classes intentionally unmapped.
- **SQLQuery live composition**: samples no longer ship build-time
  `setup.sql`. The worker derives the composition DDL per run — Pyodide
  emits text only (plan + view SQL + render); DuckDB-WASM executes and
  introspects columns; edits can never leave a stale composition.
- **Gallery suites**: `?suite=general|uscore|omop` filters the dropdown
  (optgroups), default sample = first of the active suite; a pill clears
  the filter. OMOP suite = person, encounters, medications (VD),
  medications (SQLQuery).
- **Staging**: inserts are batched (150 rows) — one 20 MB VALUES
  statement crashed DuckDB-WASM's heap.
