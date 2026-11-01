# GLOBAL KNOWLEDGE

Read `GLOBAL_RULES.md` first. This is compact durable memory for the
spec-compliance rerun. Detailed evidence remains in `ARCHIVE_LOG.md`,
`spec_comp/FP-01..FP-20/`, `spec_comp/CQL-01..CQL-22/`,
`spec_comp/SOF-VD-01..13/` handoffs, and
`spec_comp/reviews/review-{5..55}.md`; do not reuse archived evidence as a
substitute for fresh probes.

## Current State

- Completed/finalized chunks are owned by the outer orchestrator; archive and
  schedule advancement are out of scope for inner passes.
- Full conformance baseline: **2832/2832** (ViewDefinition 144/144, FHIRPath
  935/935, CQL 1706/1706, DQM 47/47). PROC_VALIDATION baseline refreshed to match.
- FHIRPath campaign FP-01..FP-20 (2026-08-16..19) COMPLETE; CQL campaign
  CQL-01..CQL-22 COMPLETE (2026-08-19..23); ViewDefinition section
  SOF-VD-01..13 COMPLETE and release-ready (2026-08-24, review-55 CLEAN).
- Analytics Layer chunks SOF-SQ-01..03 remain scheduled — see "Analytics
  Layer Watch-Items" below before starting them.
- Milestone-4 reconciliation (2026-08-19) re-landed sibling-session-clobbered
  fixes; integration parity now 7 failed / 765 passed (residuals: 2 std::regex
  named-group limits + 5 fallback temporal-edge expectation mismatches,
  untriaged). See "Sibling-Session Clobber Hazard" below.
- Native `fhirpath.duckdb_extension` (and `cql.duckdb_extension`) must be
  rebuilt and redeployed (repo bundle AND user site-packages) after any
  evaluator.cpp / cql_extension.cpp change; stale committed binaries caused
  ~108 phantom parity failures (diagnosed 2026-08-19).
- Release 0.0.8 hardening (Domains 1–10, iterations 11–19) complete;
  `QA-001`..`QA-010` verified.
- Premature CQL-16/SKEPTIC artifacts quarantined under `spec_comp/misfires/`;
  must not be counted as evidence.
- Carry-forward review findings are listed under Open Review Findings below.

## Evolution Statistics

Each row: chunk/personality → outcome + one-line essence. Full probe paths,
case counts, and methodology live in `spec_comp/<chunk>/` handoffs and
`ARCHIVE_LOG.md`.

| Chunk/launch | Personality | Issues | Essence |
| --- | --- | ---: | --- |
| SOF-SQ-01 Analytics Layer SQLQuery/SQLView | SKEPTIC | 2 H/4 M fixed | Mandate's canonical/type-code claims BOTH wrong vs machine FSH (branch upstream/sqlquery-view-sources): IG base hl7.org/fhir/uv (dual-form recognition added), SQLView type=sql-view not sql-query, parameter 0..* not 1..*. Strict base64, use 1..1, ASCII sql-name regex, to_dict roundtrip. 55/55 + gate 2832/2832. Archive: ARCHIVE_LOG.md. |
| SOF-SQ-02 Runner/binding/execution | SKEPTIC | 1 H/4 M fixed | Registry DuckDB type computed but never APPLIED to temporal params — 'not-a-date' bound as VARCHAR gave silent wrong results; now prepared-CAST to registry type + typed errors. bool-as-int guard, int32/64 signed range, Decimal accepted, FHIR partial dates normalized to earliest instant. Injection-safe param path; cycles complete incl. root-inclusive. 89/89 + gate 2832/2832. Archive: ARCHIVE_LOG.md. |
| SOF-SQ-02 (2nd) | HISTORIAN | 1 M/1 L fixed | Python-native temporal params bypassed coercion entirely (time-for-date, date-for-time bound verbatim) — same defect class as SKEPTIC QA-001 on the value-kind axis; _TEMPORAL_KINDS registry + uniform CAST. Mixed-graph ordering, 120 params, dialect-content binding, injection, collisions, mid-chain failure all verified clean (spec: materialization strategy is implementation-defined). 94/94 + gate 2832/2832. Archive: ARCHIVE_LOG.md. |
| SOF-SQ-02 (3rd) | EXPLORER | 2 H fixed | Official spec-example ':name' placeholders raw ParserException (DuckDB accepts only $name/?); ':name'→'$name' token rewrite, literal/comment/::-cast aware, values still prepared-bound. Tz-aware native datetimes bound host-tz-dependently and inconsistently with string spelling of the same instant; normalize to naive wall time pre-CAST. Dependency mechanics clean (30-deep, post-DROP rebuild, idempotent, interleaved). 102/102 + gate 2832/2832. Archive: ARCHIVE_LOG.md. |
| SOF-VD-13 CanonicalResource/cnl/sql-name/extra_fields | SKEPTIC | 0/0 | CLEAN. cnl invariants vs build.fhir.org; sql-name on name/Column.name/Constant.name; extra_fields verbatim round-trip (no relatedArtifact in v2 SD); tag namespace warning only without '/'. Intentional cnl-1 ERROR-on-url strictness logged. Archive: spec_comp/SOF-VD-13/. |
| SOF-VD-13 (2nd) | HISTORIAN | 1/0 | cnl-1 on url demoted ERROR→WARNING (official SD XML severity=warning; sof-js does not check url). New types.py cnl1_url_warning(); builtin-vs-constant precedence matches RI Object.assign order. Archive: spec_comp/SOF-VD-13/. |
| SOF-SQ-01 (2nd) | HISTORIAN | 1 H/1 M/3 L fixed | Full FSH differential: to_dict roundtrip data loss (known-but-unmodeled fields + per-entry extras + verbatim meta/type; canonical never rewritten), status 1..1, param.type FHIR-primitive registry validation, LibraryTypesCodes system fixity. 70/70 + gate 2832/2832. Archive: ARCHIVE_LOG.md. |
| SOF-SQ-01 (3rd) | EXPLORER | 3 LOW/0 | CLEAN. Volume+edge battery (100 content, 50 RA, 64 params, base64/urlsafe/padding/BOM/1MB, dispatch ambiguity, malformed shapes, 3-gen mutation-stable roundtrip, e2e runner): all rejections typed with per-entry index; 2 INTENDED (strict base64, foreign-system coding) + 1 DEFERRED (runner rejects ;charset= contentTypes — parse side spec-correct). 70/70 + gate 2832/2832. Archive: spec_comp/SOF-SQ-01/. |
| SOF-VD-13 (3rd) | EXPLORER | 2 LOW/0 | Warn-worthy urls still generate+execute; cnl-0 gate fixed to ASCII [A-Z] (str.isupper unicode-loose); QA-002 INTENDED: generate_view_sql swallows warnings (validate_view_definition is the capture API, matches sof-js). Archive: spec_comp/SOF-VD-13/. |
| SOF-VD-12 Profiling/Shareable/Tabular | SKEPTIC | 1 HIGH/0 | FIXED: profile recognition used INVENTED canonicals (sql-on-fhir.org/ig) — real ones are http://hl7.org/fhir/uv/sql-on-fhir/...; data-driven SHAREABLE/TABULAR_..._PROFILE_CANONICALS alias frozensets in viewdef/metadata.py. Archive: spec_comp/SOF-VD-12/. |
| SOF-VD-12 (2nd) | HISTORIAN | 0/0 | CLEAN. Enumerated FULL differential of actual Shareable/Tabular SDs (HL7/sql-on-fhir HEAD == ig/2.0.0) — rule set complete; enforcement at all nesting depths; foreign canonicals ignored+retained (sof-js never inspects meta.profile); plain VD without status parses (official validator outranks prose); 2.0.0 Binary examples round-trip byte-identical. Archive: spec_comp/SOF-VD-12/. |
| SOF-VD-12 (3rd) | EXPLORER | 1 MED/0 | Constant valueDecimal: json.dumps(to_dict()) TypeError (Decimal leak) — _json_number_value (int/float/typed ValueError >17 digits; dataclass keeps Decimal). Combined profiles through nested unionAll; XML typed-rejected. Archive: spec_comp/SOF-VD-12/. |
| SOF-VD-11 View Runner + IG Examples | SKEPTIC | 1/0 | 5/5 IG 2.0.0 Binary examples parse+generate+execute; type coercion pinned native==fallback; spec_tests NO DRIFT; FORWARD DRIFT: upstream HEAD moved to v3.0.0-ballot examples (rejected by 2.0.0 parser — report for re-sync). Fixed dead SET allow_unsigned_extensions retry in extension.py. Archive: spec_comp/SOF-VD-11/. |
| SOF-VD-11 (2nd) | HISTORIAN | 0/0 | CLEAN. Multi-resource shared tables (resourceType filter, no leakage); materialized views catalog types VARCHAR for temporal columns; 4 concurrent sessions isolated; typed error boundaries; generate_view_sql public surface. Local /mnt/d/sql-on-fhir-v2 is a STALE 2024 fork — drift checks via gh API on FHIR/sql-on-fhir.js. Archive: spec_comp/SOF-VD-11/. |
| SOF-VD-11 (3rd) | EXPLORER | 2/0 | 1200-patient volume exact; orjson ~127-level nesting ceiling made fallback silently return [] — _json_serialize falls back to _json_serialize_iterative. run_all.py DQM child drvfs flake left STALE 47/47 report — absolute paths + one bounded retry. Archive: spec_comp/SOF-VD-11/. |
| SOF-VD-10 validation sweep | SKEPTIC | 0; 2 LOW INTENDED | sql-name regex no length cap (65/1000-char OK); combos/required fields/binding intact; profile no 2.0.0 constraint → pipe/hash acceptance compliant; plain ValueError at dataclass __post_init__ fine (SQLOnFHIRError subclasses ValueError). Archive: spec_comp/SOF-VD-10/. |
| SOF-VD-10 (2nd) | HISTORIAN | 0; 1 LOW DEFERRED | Reference validator source settles schema questions (constant items lack additionalProperties:false; FHIR integer forbids decimal point). Maximal-valid-VD round-trip. DEFERRED: Decimal in Constant.to_dict / Decimal-aware serializer API. Archive: spec_comp/SOF-VD-10/. |
| SOF-VD-10 (3rd) | EXPLORER | 1 MED/0 | Raw RecursionError escaped parse_view_definition at ~1000+ deep nesting — typed ParseError restored; resourceType in v2 fixtures is the FULL canonical URL. Archive: spec_comp/SOF-VD-10/. |
| SOF-VD-09 root ViewDefinition.where | SKEPTIC | 1 MED/0 | 0..* AND semantics; exclusion via exact `fhirpath_json(...)='[true]'`; %constants incl. backticks; fixed non-array/list-of-strings/unknown-key where shapes (schema is array-of-objects additionalProperties:false; permissive validate_where_conditions retained). Archive: spec_comp/SOF-VD-09/. |
| SOF-VD-09 (2nd) | HISTORIAN | 1 HIGH/0 | `%rootResource.`/`%resource.`-prefixed expressions with focus operands silently evaluated against ROOT inside iterators (order-dependent guard) — AST spine walk `_prefix_tail_has_focus_operand`; both orderings now raise typed ValidationError. Archive: spec_comp/SOF-VD-09/. |
| SOF-VD-09 (3rd) | EXPLORER | 0; closed | 56 AND-chained wheres → ONE flat WHERE; guard holds at depth/unionAll; collection-boolean where results EXCLUDE per singleton-true doctrine (pin); 5KB unicode descriptions round-trip. Archive: spec_comp/SOF-VD-09/. |
| SOF-VD-08 select.unionAll | SKEPTIC | 1 HIGH/0 | UNION ALL duplicate preservation; branch mismatch rejected (names+types+collection flags); arm model (enclosing columns on branch rows); Cartesian parts; fixed path-keyed null-row suppression killing independent siblings — suppression identity now the union wrapper instance (`_union_origin_id`). Archive: spec_comp/SOF-VD-08/. |
| SOF-VD-08 (2nd) | HISTORIAN | 1 HIGH/0 | Nested forEachOrNull+unionAll wrappers emitted one null row PER BRANCH — wrapper ids now collected in lockstep at the emission site in _process_selects (deleted _collect_union_wrapper_ids). Archive: spec_comp/SOF-VD-08/. |
| SOF-VD-08 (3rd) | EXPLORER | 1 HIGH/0 | Fixed backtick constant refs %`name` silently empty (iter_constant_references backtick skip-region). Pin: SD 2.0.0 has NO select.where — per-focus select.where is fhir4ds EXTENSION doctrine; collection=true branches with both types unset pass (sof-js compares names only). Archive: spec_comp/SOF-VD-08/. |
| SOF-VD-07 select.repeat | SKEPTIC | 1 MED/0 | 19 repeat.json fixtures end-to-end; Python recursion-budget segfault at ~14k depth — _run_with_recursion_budget worker thread (benefits ALL FHIRPath UDFs). INTENDED pins: value-dedup (=) union collapse; row order unpinned; primitive-yielding repeat empty. Archive: spec_comp/SOF-VD-07/. |
| SOF-VD-07 (2nd) | HISTORIAN | 0; 4 LOW INTENDED | Expression-typed repeat paths (where()/|, %resource/%context per-node, quote escaping, $this fixpoints) all conformant with parity. Archive: spec_comp/SOF-VD-07/. |
| SOF-VD-07 (3rd) | EXPLORER | 1 HIGH/0 | Python fallback dropped elements whose ONLY key is `extension` — `_is_shadow_extension` provenance flag (assert provenance, not key shape); 12-path/1000-wide/6000-deep trees. Archive: spec_comp/SOF-VD-07/. |
| SOF-VD-06 forEach/forEachOrNull | SKEPTIC | 0; 2 LOW DOC | Process(S,N) + sof-js audit: combo rejection; forEachOrNull empty → exactly one null row (%rowIndex=0, collection cols NULL not []); %rowIndex/%context/%resource semantics; duplicate JSON keys last-wins; select.where per-focus pinned. Archive: spec_comp/SOF-VD-06/. |
| SOF-VD-06 (2nd) | HISTORIAN | 0; 2 LOW INTENDED | column+forEach canonical spec form; forEach-in-unionAll canonical example reproduced; column.constant rejected; %parent rejected; forEach+unionAll same select accepted (spec-silent). Archive: spec_comp/SOF-VD-06/. |
| SOF-VD-06 (3rd) | EXPLORER | 0; closed | Heavy-FHIRPath targets; JSON-null array elements excluded from collections; forEach errors degrade uniformly to empty; list-valued %constant inexpressible per SD; 5 flat JOIN LATERALs deterministic. Archive: spec_comp/SOF-VD-06/. |
| SOF-VD-05 Nested select | SKEPTIC | 2 MED + 1 LOW | select.select recursion only — NO user-facing contentReference in any v2 version; fixed unknown-select-field silent drop + present-empty column/select arrays (validator additionalProperties:false + minItems:1). Archive: spec_comp/SOF-VD-05/. |
| SOF-VD-05 (2nd) | HISTORIAN | 0; 1 LOW INTENDED | SKEPTIC fixes regression-free at depth-3/unionAll; INTENDED: fhirpath_repeat collects dict elements only; column type must match FHIR primitive at runtime; repeat is an ARRAY of paths. Archive: spec_comp/SOF-VD-05/. |
| SOF-VD-05 (3rd) | EXPLORER | 0; 1 LOW INTENDED | Process(S,N) Formal Semantics: columns evaluate against ITERATED focus; sibling/nested/unionAll 'parts' combined by CARTESIAN PRODUCT ('Sibling selects are effectively cross joined'); empty part suppresses ALL rows for that focus; heterogeneous unionAll branches rejected at generate. Archive: spec_comp/SOF-VD-05/. |
| SOF-VD-04 Column collection/type/tag | SKEPTIC | 1 MED + 1 LOW | Unknown keys in column/tag accepted → parser allowlist; element-ID type naming a different resource now reported; collection=true emits LIST; non-primitive without type errors at runtime. Archive: spec_comp/SOF-VD-04/. |
| SOF-VD-04 (2nd) | HISTORIAN | 1 LOW | `_is_element_id_type` misclassified dotted absolute URIs — now requires colon-free dotted path. Anchored to ig/2.0.0 SD (releases branch; live CI serves v3.0.0-ballot). Archive: spec_comp/SOF-VD-04/. |
| SOF-VD-04 (3rd) | EXPLORER | 1 LOW | Mixed-type collections, type-URI matrix, 125-tag volume, unionAll collection-flag mismatch, whitespace-only tag allowed (validate_tag_string). Archive: spec_comp/SOF-VD-04/. |
| SOF-VD-03 Select | SKEPTIC | 1 LOW + 1 DEF | Sibling selects CROSS JOIN (launch "UNION" hypothesis WRONG); unionAll mismatch at GENERATION is fine; preflight text drift fixed. Archive: spec_comp/SOF-VD-03/. |
| SOF-VD-03 (2nd) | HISTORIAN | 0; 1 DEF + 1 INT | processing_model.md normative; strict_collection opt-in; IG-clone /tests/*.json STALE DRAFT fixtures — authoritative = sql-on-fhir.js snapshot. Archive: spec_comp/SOF-VD-03/. |
| SOF-VD-03 (3rd) | EXPLORER | 0 | Deep nesting/sibling×unionAll×forEach/collection at depth clean; union.json is ground truth for arm composition; models.fsh stricter than fixtures (names AND TYPES). Archive: spec_comp/SOF-VD-03/. |
| SOF-VD-02 Constants | SKEPTIC | 1 MED | integer64 outside FHIRPath int32 literal range → typed ConstantResolutionError; constants substituted TEXTUALLY (must satisfy FHIRPath literal grammar). Archive: spec_comp/SOF-VD-02/. |
| SOF-VD-02 (2nd) | HISTORIAN | 2 MED | Decimal serialization: fixed-point (no exponent, N1 grammar), parse_float=Decimal. DEFERRED: extreme-exponent memory amplification. Archive: spec_comp/SOF-VD-02/. |
| SOF-VD-02 (3rd) | EXPLORER | 1 MED + 1 DEF | Bare boolean-constant column falsely rejected (regex classifier matched keyword literals). DEFERRED: constants named after builtins never substituted (spec-silent). Archive: spec_comp/SOF-VD-02/. |
| SOF-VD-01 Root | SKEPTIC | 1 HIGH | FHIR_VERSION_CODES stale — determine IG fhirVersion from sushi-config.yaml; fixture metadata is NOT the binding. Archive: spec_comp/SOF-VD-01/. |
| SOF-VD-01 (2nd) | HISTORIAN | 1 MED + 1 INT | KNOWN_FHIR_RESOURCE_TYPES refreshed (R6 DeviceAlert); 39 legacy codes intentional superset; fetch value sets as JSON not HTML. Archive: spec_comp/SOF-VD-01/. |
| SOF-VD-01 (3rd) | EXPLORER | 1 HIGH | fhirVersion ValueSet UNFILTERED — fixed with full 60-code 6.0.0-ballot4 codesystem list; a codeset fix must match the FULL concept expansion. Archive: spec_comp/SOF-VD-01/. |
| CQL-22 L3 | EXPLORER | 1 MED | 'return N.given' SILENTLY DROPPED the where clause (WHERE wrapped scalar source, RETURN rebuilt raw) — fixed in _query.py, general bug. Message raise is a free oracle for swallowed evaluation paths. spec_comp/CQL-22/. |
| CQL-22 L2 | HISTORIAN | 0; 1 INT | Composition contexts all conformant. INTENDED: informational channel (Trace/Message/Warning) unimplemented by design; test XML pins 4 cases. spec_comp/CQL-22/. |
| CQL-22 L1 | SKEPTIC | 0; 1 INT | App B semantics verified both engines: only Error stops evaluation, default severity Message, null condition generates nothing. Lesson: grep the fixture list before declaring 'fixtures don't pin it'. spec_comp/CQL-22/. |
| CQL-21 L1 | SKEPTIC | 1 HIGH | Age family routed through §22.21 uncertainty engine on ALL surfaces; age→VARCHAR broke 11 DQM measures via raw SQL BETWEEN — fixed both bound branches with cqlUncertainCompare. No CqlAgeOperatorsTest.xml pin; spec prose governs. Stale-binary hazard bit again. spec_comp/CQL-21/. |
| CQL-21 L2 | HISTORIAN | 1H+2M; 2 DEF | VARCHAR-age consumers: `age in {9,36}` silent FALSE (in-list → OR of cqlUncertainCompare); list Min/Max lexicographic; unary '-'/Max(age,30) BinderExceptions. Repaired STALE site-packages cql binary (verify md5 at launch START). spec_comp/CQL-21/. |
| CQL-21 L3 | EXPLORER | 1H+2M | Retrieved-code `=` vs literal Code ALWAYS False (coding_matches_exact UDF); Sum over §22.21 intervals dropped uncertain elements (cqlUncertainListSum); `Average` keyword missing from registries. Lesson: audit comparison lowerings in PAIRS. spec_comp/CQL-21/. |
| CQL-20 L1 | SKEPTIC | 6 (5 HIGH) | Dynamic/derived operands: Min/Max/Median over query-derived Quantities saw only FIRST row; FHIR choice-cast names never canonicalized; cte_manager UNKNOWN unwrap corrupted _pt correlation. New _translate_list_aggregate_dispatch + _element_rows_define_list (CTE-backed). spec_comp/CQL-20/. |
| CQL-20 L2 | HISTORIAN | 2H+1M | Dynamic query-element aggregates lost Decimal exactness; non-numeric operands leaked BinderExceptions. Inference widening is high blast-radius — ALWAYS run DQM after inference edits. spec_comp/CQL-20/. |
| CQL-20 L3 | EXPLORER | 1M; 2 DEF | Statistical family corrupted at ≥1e10 (DOUBLE casts) — shifted-deviation exact-DECIMAL lowering at all three tiers. GeometricMean ≥1e13 and aggregates-over-query-source DEFERRED. spec_comp/CQL-20/. |
| CQL-19 L1 | SKEPTIC | 5 (4 HIGH) | Whole family broken over dynamic/stored-list operands (CQL-18 machinery was Part-1 only). REGRESSION CAUGHT: RetrievePlaceholder must stay rows-shaped through union dispatch. Adjudications pinned in NOT A BUG registry. spec_comp/CQL-19/. |
| CQL-19 L2 | HISTORIAN | 4 (3 HIGH) | Count over rows-union wrapped as scalar subquery; singleton-from stored-list alias returned whole list (rows-vs-elements cardinality); opaque binder error → typed TranslationError. spec_comp/CQL-19/. |
| CQL-19 L3 | EXPLORER | 2 HIGH | Union over alias-of-alias stored-list defines emitted 2-column CTE into scalar context (stored-list meta through Identifier aliases, PEER-shape-guarded); Tail/Skip/Take/Length/SingletonFrom over retrieve-shaped operands (_list_operator_full_list_source). spec_comp/CQL-19/. |
| CQL-18 L4 | SKEPTIC | 6 (1 CRIT) | Literal surface conformant 3 launches while EVERY dynamic multi-valued path (name.given) was broken — centralized _promote_fhirpath_text_list() across all list-macro helpers. fhirpath_text truncation is a standing trap for list-valued consumers. spec_comp/CQL-18/. |
| CQL-18 L5 | HISTORIAN | 4 (1 CRIT) | Define-alias of dynamic multi-valued property mis-shaped in every list consumer — new DefinitionMeta.stores_list_value discriminator (List< type alone is NOT it); property chains over retrieve defines truncated (FHIRSchemaRegistry.is_multi_valued_element). spec_comp/CQL-18/. |
| CQL-18 L6 | EXPLORER | 5 (1 CRIT) | DEEP 0..* navigation over retrieve-define aliases; inline CHAINED list operators raised 'Table function cannot contain subqueries'; includes/included-in null-element divergence. spec_comp/CQL-18/. |
| CQL-17 L1 | SKEPTIC | 3 (1 HIGH) | Typed-null `null as Interval<T>` union → BinderException. Lesson: probe TYPED-NULL operands through EVERY dispatch; when one sibling gets a shape fix, audit ALL siblings. spec_comp/CQL-17/. |
| CQL-17 L2 | HISTORIAN | 4 (2 HIGH) | No-precision `same as`/`same or after/before` on numeric intervals misrouted to cqlDateTimeEqual; native width/size NULL on mixed Integer/Decimal bounds; Quantity bound JSON shape diverged between emission sites. spec_comp/CQL-17/. |
| CQL-17 L3 | EXPLORER | 1 HIGH | Arithmetic over interval-derived scalars misrouted to temporal add — _interval_scalar_point_kind gate. Width/Size exactness pinned (see NOT A BUG). spec_comp/CQL-17/. |
| CQL-16 L1 | SKEPTIC | 2 (1 HIGH) | Interval-in-interval `in` keyword raised BinderException; closed null bounds not sentinelize in meets/on-or family. Reference Interval.start/.end getters are the decisive oracle. INTENDED pins in registry. spec_comp/CQL-16/. |
| CQL-16 L2 | HISTORIAN | 2 MEDIUM | Long null-bound sentinels were int32 — TWO parallel native sentinel tables (interval.cpp AND cql_extension.cpp) must move in lockstep; Quantity null closed bounds → Quantity(MIN/MAX_DECIMAL, unit) sentinels. spec_comp/CQL-16/. |
| CQL-16 L3 | EXPLORER | 2 HIGH | Native intersect propagated open flags; native compare flagged Integer-vs-Decimal bounds incomparable → NULL or WRONG DETERMINISTIC FALSE. Probe MIXED POINT TYPES; include the no-python engine. spec_comp/CQL-16/. |
| CQL-15 L1 | SKEPTIC | 4 (2 HIGH) | `ends <prec>` compared end-equality only; `collapse(X,per)` mistranslated as collapse(expand(X,per)) — dedicated collapse_intervals_per UDF. spec_comp/CQL-15/. |
| CQL-15 L2 | HISTORIAN | 5 (3 HIGH) | Temporal per of 0/1 must run meets/overlaps at PER-UNIT precision; `includes [prec]` collapsed determined results to NULL. Lesson: never trust an inherited gate claim — rerun the gate after the last edit. spec_comp/CQL-15/. |
| CQL-15 L3 | EXPLORER | 2 (1 HIGH) | LIST_EXTRACT interval operands missing from recognizers; Expand truncating the HIGH bound regressed official ExpandPerHourOpen — caught by fresh gate. spec_comp/CQL-15/. |
| CQL-14 L1 | SKEPTIC | 2 (1 HIGH) | Bare `same as` on intervals/points fixed; Now() 3-digit ms; mixed Time/DateTime null. DateTime.getNormalized normalizes only above DAY precision. spec_comp/CQL-14/. |
| CQL-14 L2 | HISTORIAN | 2 (1 HIGH) | No-precision `same or after/before` on interval operands compared LOW-vs-LOW natively — fixed at translator. Lesson: probe OTHER OPERAND SHAPES of sibling forms a prior pass fixed. spec_comp/CQL-14/. |
| CQL-14 L3 | EXPLORER | 2 HIGH | Parser consumed `same <prec> or after|before` OR-token as `as`; `starts/ends on or before|after <prec> of X` hardcoded DATE casts ignoring `precision of`. cql-to-elm Kotlin is the decisive oracle. spec_comp/CQL-14/. |
| CQL-13 L1 | SKEPTIC | 2 (1 HIGH) | difference in weeks used duration math instead of §8.7 boundary counting; Date + sub-day quantity → NULL. 20+ of 22 candidates were probe-expectation errors. spec_comp/CQL-13/. |
| CQL-13 L2 | HISTORIAN | 2 (1 HIGH) | Sub-day Difference reused Duration truncation (10:30→12:15 in hours: 2 not 1; C++ floor division pre-1970); Time + week/day units silent no-op. spec_comp/CQL-13/. |
| CQL-13 L3 | EXPLORER | 3 (2 HIGH) | Years/months duration with month-precision operand returned crisp max instead of uncertainty interval (midnight convention); Python nulled durations with tz-aware end (_wall_clock() strips tzinfo). Internal inconsistency is a bug oracle. spec_comp/CQL-13/. |
| CQL-12 L1 | SKEPTIC | 1 HIGH | Bracket indexing a scalar String-valued define returned NULL — dispatch keyed on 'expression contains Retrieve' instead of value SHAPE (RowShape is the correct key). Always probe through NAMED DEFINES. spec_comp/CQL-12/. |
| CQL-12 L2 | HISTORIAN | 1 MEDIUM | Combine over chained property navigation → opaque BinderException (macro CASE type-guards do NOT protect lambdas). spec_comp/CQL-12/. |
| CQL-12 L3 | EXPLORER | 2 (1 HIGH) | SplitOnMatches capture-group interleave leak; bracket indexing over chained navigation character-indexed the collapsed scalar — route by SOURCE SHAPE. spec_comp/CQL-12/. |
| CQL-11 L1 | SKEPTIC | 3 (1 HIGH) | `div` lowered through DOUBLE `/` (0.3 div 0.1 → 2) — exact cqlDivide; Power underflow '%.15g' text rounded UP by VARCHAR→DECIMAL cast. Probe DOUBLE corruption ADJACENT to integer boundaries. spec_comp/CQL-11/. |
| CQL-11 L2 | HISTORIAN | 2 HIGH | Round/RoundTo used bare FLOOR overridden by the CQL Floor macro (use system. prefix inside composite macros); Decimal literal overflow raised instead of null. spec_comp/CQL-11/. |
| CQL-11 L3 | EXPLORER | 4 (2 HIGH) | Statically-Integer NON-literal successor/predecessor boundary returned out-of-range BIGINT (re-probe literal-only fixes through a non-foldable wrapper); parse_expression dropped trailing tokens. spec_comp/CQL-11/. |
| CQL-10 L1 | SKEPTIC | 5 (3 HIGH) | High/LowBoundary Decimal fill-and-truncate (reference impl + fixtures outrank prose); Ceiling/Floor Integer-extent null; Integer+Long INT32 overflow. Fetch the HL7 reference implementation (cqframework Kotlin) to settle prose conflicts. spec_comp/CQL-10/. |
| CQL-10 L2 | HISTORIAN | 2 (1 HIGH) | Decimal boundary DOUBLE corruption at translator seam AND Python UDF float() return — exact-Decimal doctrine must be audited END-TO-END. PYTHONPATH trap re-bitten. spec_comp/CQL-10/. |
| CQL-10 L3 | EXPLORER | 2 (1 HIGH) | Q/Q Divide did not cancel commensurable units (pint to_reduced_units + native ratio). Unit ALGEBRA vs unit CONVERSION are different code paths. spec_comp/CQL-10/. |
| CQL-09 L1 | SKEPTIC | 2 MEDIUM | List equality erased one-sided-null uncertainty (scope fix to Equal-path macros only); interval equality closed-null vs open-null. spec_comp/CQL-09/. |
| CQL-09 L2 | HISTORIAN | 2 MEDIUM | Nested-list and tuple-element equality collapsed uncertainty to false (DuckDB constraints: no macro recursion, no correlated UNNEST, no subqueries in lambdas). spec_comp/CQL-09/. |
| CQL-09 L3 | EXPLORER | 2 MEDIUM | Bare-numeric vs Quantity comparisons dropped units — spec-strict GLOBAL promotion regressed DQM (fixtures pin NUMERIC comparison for dynamic FHIR quantities); scope promotion to static literals. Stale doctrine corrected: 5 'mg' = 5 → null. spec_comp/CQL-09/. |
| CQL-08 L1 | SKEPTIC | 1H+1M | Artificial Coalesce arity cap removed (spec variadic); mixed-type Coalesce uniform typed error. INTENDED pins in registry. spec_comp/CQL-08/. |
| CQL-08 L2 | HISTORIAN | 2M+1L | ToInteger/ToLong(Decimal) truncation REVERTED — Table 9-E has no such row (an earlier landed 'fix' was spec-wrong; re-verify prior-launch spec claims live); nested Coalesce escaped the type guard. spec_comp/CQL-08/. |
| CQL-08 L3 | EXPLORER | 0; 1 INT + 1 DEF | Query-valued `is (not) null` is EXISTENTIAL in eCQM content — strict-spec folding regressed DQM 47→41, REVERTED; literal-list path stays strict. DEFERRED: query alias colliding with library define name. spec_comp/CQL-08/. |
| CQL-07 L2 | HISTORIAN | 1 HIGH | ToQuantity(Quantity) identity returned NULL ('{'-prefixed dispatch funnels fragile); ConvertsToT↔ToT twin invariant. Walk Appendix B rows exhaustively. spec_comp/CQL-07/. |
| CQL-07 L3 | EXPLORER | 0; 1 INT | Conversion chains/round-trips clean. INTENDED: sub-millisecond fractional literals → null. Harness: e2e defines must run via translate_library_to_population_sql. spec_comp/CQL-07/. |
| CQL-06 L1 | SKEPTIC | 1 HIGH | ToQuantity/ConvertsToQuantity rejected bare calendar-duration keywords ('5 years') that §ToQuantity admits. spec_comp/CQL-06/. |
| CQL-06 L2 | HISTORIAN | 1 HIGH | ToString(4 days) must emit bare-keyword form '4 days' (Table 9-G round-trip). NOT A BUG: ConvertsToLong(2147483648) error correct. spec_comp/CQL-06/. |
| CQL-06 L3 | EXPLORER | 1H+2M | FHIR primitive `.value` accessor returned NULL on every primitive — _strip_primitive_value_segments (FHIRHelpers load-bearing). ToTime tz rejection REVERTED (fixtures mandate offset acceptance). spec_comp/CQL-06/. |
| CQL-05 L1 | SKEPTIC | 2H+2M+1DEF | Bare-retrieve First/Last/singleton-from emitted CTE-name-as-column SQL; Children/Descendants query-source aliases bound whole list; FHIR string-family `is String` (data-driven map). DEFERRED QA-005/107. spec_comp/CQL-05/. |
| CQL-05 L3 | EXPLORER | 2H+1M | Strict-cast-in-arithmetic TRY+volatile binder error; element access over retrieve-bound defines (coercion must be consumer-site — generic LIST aggregation regressed DQM 47→28); fhirpath_text returns only first element. spec_comp/CQL-05/. |
| CQL-04 L1 | SKEPTIC | 1 INT + 1 DEF | 3VL matrices clean. INTENDED: population-SQL Boolean surface collapses null→FALSE; expression-level 3VL preserved. spec_comp/CQL-04/. |
| CQL-04 L2 | HISTORIAN | 1 HIGH | Unary `not` parsed at wrong tier — per official cql.g4 notExpression sits between and-tier and comparisons. spec_comp/CQL-04/. |
| CQL-04 L3 | EXPLORER | 3 HIGH | HISTORIAN's precedence doctrine was BACKWARDS — ANTLR earlier alternatives bind TIGHTER; case-expression collapse; Boolean-define-alias 3VL destruction. Don't just READ the grammar, RUN it. spec_comp/CQL-04/. |
| CQL-03 L1 | SKEPTIC | 2H+1 INT | Strict _validate_datetime_literal; `5 'xyz' = 5 'xyz'` C++ True vs spec null — same_code_unit_valid_for_compare guard ('{dose}', 'mm[Hg]', 'mg/m2' valid). spec_comp/CQL-03/. |
| CQL-03 L2 | HISTORIAN | 2H+1M | Quantity validity now STRUCTURAL UCUM grammar (is_valid_ucum_atom, both engines); Ratio tuple selector folds to canonical JSON. DEFERRED: cross-code prefixed-unit conversion null (FP-18 family). spec_comp/CQL-03/. |
| CQL-03 L3 | EXPLORER | 3H+3M | Temporal property accessors (.month/.year/.hour/.date/.time) returned null; CQL 1.5.3 combined seconds/ms precision. NOT A BUG: E-notation literals rejected. spec_comp/CQL-03/. |
| CQL-02 L1 | SKEPTIC | 4H+1 INT | Code/Concept `~` case-insensitive on code+system; named-code Concept members double-serialized; `.codes` accessor returned one code. INTENDED: static Code-in-CodeSystem membership structural. spec_comp/CQL-02/. |
| CQL-02 L2 | HISTORIAN | 2H+1M | Define-alias ValueSet/CodeSystem membership emitted clinical JSON as raw IN operand (alias-chain resolution); empty `Concept { }` folds to empty codes; fallback in_valueset NULL+warn-once. spec_comp/CQL-02/. |
| CQL-02 L3 | EXPLORER | 2 HIGH | Absent-vs-explicit-null Code element asymmetry in =/~; `(Concept).codes ~ List<Code>` fell to byte-wise JSON — element-wise fold. spec_comp/CQL-02/. |
| CQL-01 L1 | SKEPTIC | 6 | Int/Long overflow crash → TRY()+typed CAST extents; `maximum Decimal + maximum Decimal` lowered to `||`; ToDecimal >8-scale HALF_UP; Truncate→INTEGER. DuckDB TRY() cannot wrap volatile fns. spec_comp/CQL-01/. |
| CQL-01 L2 | HISTORIAN | 3 | `/` used DuckDB division (DECIMAL→DOUBLE) — exact cqlDivide; list Sum/Avg via DOUBLE — native exact list sums; DECIMAL exprs break COALESCE with VARCHAR. Probe spec-example lines verbatim. spec_comp/CQL-01/. |
| CQL-01 L3 | EXPLORER | 2H+1 INT | Definition-alias scalar subqueries forced TRY_CAST AS DOUBLE — cast keyed on definition_meta.cql_type. INTENDED: >extent Decimal literals ≤28 int digits fixture-pinned VALID. spec_comp/CQL-01/. |
| FP-20 §9-§12 (3 launches) | all 3 | 3 LOW INTENDED + 4 fixed | %context = ORIGINAL node through select/where; %resource/%rootResource = host-layer vars; type() = {namespace,name} only; as()/is() exact-vs-subtype asymmetry (FP-15 fixture doctrine); tuple literals rejected conformant; Meta.profile→canonical / Meta.source→uri typing fixed data-driven; sibling session overwrote evaluator.cpp mid-run (see hazard). Archive: spec_comp/FP-20/. |
| FP-19 §7-§8 (3 launches) | all 3 | 1 fixed + 2 INTENDED + 1 DEFERRED | $index 0-based; init evaluated once; one-arg aggregate $total starts EMPTY (fixture-canonical); native incompatible-operand arithmetic now throws; mixed-unit +/- most-granular input unit. DEFERRED: derived/prefixed UCUM ('kN'). Archive: spec_comp/FP-19/. |
| FP-18 §6.6/§6.7 (3 launches) | all 3 | 7 fixed + 3 INTENDED + 2 DEFERRED | div/mod via binary64 wrong on int64 (exact paths both engines); __int128 decimal-text mod; unary-minus Long overflow; `&` complex JSON conversion; native Time ± renders bare hh:mm:ss. DEFERRED: native Quantity math in SI base vs spec most-granular. Archive: spec_comp/FP-18/. |
| FP-17 §6.5 Boolean (3 launches) | all 3 | 1 INTENDED | Truth tables clean; chained implies LEFT-associative per ANTLR grammar; non-Boolean singletons TRUTHY — toBoolean-convertible "fix" reverted by fixture. Archive: spec_comp/FP-17/. |
| FP-16 §6.4 Collections (3 launches) | all 3 | 2 fixed | membership()/contains() helpers returned {} for multi-item singletons; union chains first-occurrence dedup; union seeds into repeat() fixpoint. Archive: spec_comp/FP-16/. |
| FP-15 §6.3 Types (3 launches) | all 3 | 15 fixed + 1 DEFERRED | KEY DOCTRINE: is/as ASYMMETRY (is subtype, as/ofType EXACT) — a prose-driven subtype fix was reverted via conformance. Native infix is/as chain left-recursion loop; hierarchy merge order; choice-assertion rescue; Meta.profile/source typing (3rd drifted type table — ARCH-002). Archive: spec_comp/FP-15/. |
| FP-14 §6.2 Ordering (3 launches) | all 3 | 10 fixed | Fractional-second comparison exactness; Date vs DateTime scale mix; native truncation at 3 digits fixed; delegate-to-engine pattern for ordering helpers. Archive: spec_comp/FP-14/. |
| FP-13 §6.1 Equality (3 launches) | all 3 | 4 fixed | Decimal `~` min precision at all native sites; Quantity `~` tolerance trailing-zero-preserving; exact yyjson int compare; `~` whitespace = {tab,LF,CR,space} only. Archive: spec_comp/FP-13/. |
| FP-12 §5.8/§5.9 (3 launches) | all 3 | 7 fixed | repeat(children()) ≡ descendants() dedup; fn_children propagates field_name/infer_fhir_type; choice-suffix rewrite; Extension typing at native inference sites. Archive: spec_comp/FP-12/. |
| FP-11 §5.7 Math (3 launches) | all 3 | 7 fixed | Exact string-power + 28-sig half-even; expandScientificToFixed (subnormal ~1% error); transcendentals binary64 shortest-round-trip; helper-math.py delegation (7th helper instance). Archive: spec_comp/FP-11/. |
| FP-10 §5.6.6-12 (3 launches) | all 3 | 8 fixed | Regex dialect parity ($-anchor PCRE, inline flags native, ASCII-class doctrine, $$ literal); named capture groups + ${name} on BOTH engines; antlr STRING loop non-greedy fix with -visitor regeneration. Archive: spec_comp/FP-10/. |
| FP-09 §5.6.1-5 (3 launches) | all 3 | 2 fixed | index_of helper contract; negative start → {} vs negative/zero length → ''. Archive: spec_comp/FP-09/. |
| FP-08 §5.5.7-9 (3 launches) | all 3 | 6 fixed | §5.5.7 year↔day/month↔day bridging violation; direct-key base bridge (J/kJ); exact decimalFactorRatio; DuckDB extension cache lesson. Archive: spec_comp/FP-08/. |
| FP-07 §5.5.4-6 (3 launches) | all 3 | 1 fixed + 2 INTENDED | `$`→`\Z` anchors; authored Z→+00:00 re-spelling removed (parity governs); Date→DateTime precision preserved; toDecimal exact at 30+ digits. Archive: spec_comp/FP-07/. |
| FP-06 §5.5.1-3 (3 launches) | all 3 | 5 fixed + 3 INTENDED | convertsToInteger('2147483648')→false (32-bit doctrine); \Z anchors; iif branch scope discipline; spec `invalid="execution"` fixtures beat older repo pins. Archive: spec_comp/FP-06/. |
| FP-05 §5.3-§5.4 | 3 personalities | 1 | Statically-known wrong-typed §5.3 args classify is_valid=True. Archive: spec_comp/FP-05/. |
| FP-04 §5.2 | 3 personalities | 1 | Native structuralFHIRComplexType() added so unmodelled JSON objects infer Quantity/Reference like Python. Archive: spec_comp/FP-04/. |
| FP-03 §5.1 | 3 personalities | 2 | Native evalBinaryOp swallowed incompatible-type comparisons as {} — decisive inside all()/exists()/where()/iif. Archive: spec_comp/FP-03/. |
| FP-02 §4.2-§4.5 | 3 personalities | 11 | UCUM exponent algebra for */÷ units; derived units (J/kJ/N/W/A/V); shared ucum_units.hpp byte-identical. Archive: spec_comp/FP-02/. |
| FP-01 §4.1 | 3 personalities | 13 | Calendar keyword canonicalization; §5.5.7 factors; -0.0034.highBoundary(1)→0.0 per fixture; exact Decimal string arithmetic native; conformance 2822→2832. Archive: spec_comp/FP-01/. |
| 1–10 (release 0.0.8 domains) | mixed | 8 | QA-001..007 verified across FHIRPath core, CQL translation, eCQM patterns, ViewDefinition, ingestion, performance, error handling, audit/DQM, installation. Archive: ARCHIVE_LOG.md. |
| 11–19 | mixed | 3 | Release hardening; QA-008..010 verified; full pytest pass. |
| 2026-07-02 | CQL-21/22 v1.0 | 3 | Concept codes ListExpression recursion; empty-system Code = wildcard (INTENDED); Message code slot any scalar token; >5-arg raises. |
| 2026-07-03 | SOF-VD-01..04 v1.0 | 3+2+3+0 | See ViewDefinition lessons above. |
| 2026-07-05 | 0.0.11 Perf + CQL | SPECIALIST/SKEPTIC | 1 | Fluent X.distinct() emitted ARRAY_DISTINCT vs order-preserving "Distinct" macro — dispatch unified. |

## Open Review Findings

- `REV-002` MEDIUM, review-25: native `fhirpath_timestamp` accepts invalid
  resource-backed DateTime strings (lexical/shape-first validation). Highest-value
  cleanup: generate native type tables from models/r4 metadata at build time.
- `REV-003` MEDIUM, review-25: `fhirpath_quantity` typed wrappers accept
  malformed Quantity-like objects.
- `REV-004` MEDIUM, review-25: native Unicode `upper()`/`lower()` use
  incomplete local case tables.
- `REV-005` MEDIUM, review-25: FHIR model/type knowledge embedded in generic
  FHIRPath runtime code instead of generated/shared model metadata
  (metadata triple-maintenance: evaluator.cpp fhirFieldType,
  models/r4/fhir_path_to_type.json, fhir_model.py).
- `REV-006` MEDIUM, review-25: FHIRPath string/STU helper arity validation
  incomplete for `trim`, `split`, `join`, `matchesFull`, `escape`, `unescape`,
  `encode`, `decode`.
- `REV-007` HIGH, review-25: qualified ValueSet references from included CQL
  libraries can lower to missing CTEs instead of resolving or raising clear
  translation errors.
- `REV-008` HIGH, review-25: generic CQL ValueSet membership embeds
  QICore-specific `qicore-notDoneValueSet` behavior.
- `REV-009` (milestone-7/8): DQM nondeterminism (CMS871 FHIRHelpers loader
  intermittent failure). TERMINAL-UNCONFIRMED as of review-55 (2026-08-24)
  after FOUR consecutive green DQM runs — do not re-open without a fresh
  reproduction; still prefer final-tree re-verification over single-pass gate
  claims.
- `REV-010` MEDIUM (milestone-8): RowShape/stores_list_value metadata model
  accumulated per-chunk syntactic DETECTION paths and peer-shape gating —
  accretion, not design. Consolidate into type inference before building
  further operator families on it.
- `REV-012` MEDIUM (milestone-9): age-uncertainty cqlUncertain* family (9
  UDFs) duplicated across Python and native; the two parsers drifted — only
  the native path is tested. Future dual-language UDF families must lock one
  fail-closed parse doctrine and add fallback-path parity tests at birth.
- `REV-013` informational (milestone-9): fhirVersion binding ships 63 codes
  (full codesystem incl. parent-level) — implementation is the more
  spec-faithful reading.
- `REV-014`: 5 fallback-side temporal±UCUM-quantity validity flag divergences
  (Python fix needed). `REV-015`: 2 native std::regex named-group/anchor gaps
  in replaceMatches. `REV-016` LOW: recursion-budget worker mutates global
  threading.stack_size()/recursionlimit under a setters-only lock.
  (Review-10; the 7 residual fhirpath parity failures, re-verified live at
  review-55.)
- Campaign code_review (2026-08-17): native `fhirpathSplitUnitTerm`
  trailing-dash `std::stoi` throw (LOW, masked); native FHIR type metadata
  duplication vs models/r4 JSON (MEDIUM — generate native tables from
  metadata next touch).
- Closed: `REV-001`, `REV-009` (CQL-06 scope), `REV-030-001`, `REV-035-001`,
  `REV-045-001`, `REV-045-002`.
- Also note: cql_tests_runner_report.json showed status "not-run" on the
  2026-08-23 final tree — CQL reference-test runner not executed that cycle.

## Sibling-Session Clobber Hazard and Single-Writer Discipline (2026-08-19)

MUST-READ before any chunk that edits shared sources (evaluator.cpp,
cql_extension.cpp, operators.py, functions/, fhir_model.py, models/r4
metadata):

- Concurrent campaign sessions share ONE working tree and ONE extension
  binary path. A race during FP-20 launch 2 OVERWROTE that launch's
  evaluator.cpp edits mid-run, and whole-file overwrites by later sessions
  silently deleted seven earlier fixes (FP-11/13/15/12/19/16 + FP-08).
- Single-writer rule: at most ONE session edits a given shared source file at
  a time. Before editing, verify your markers are still present (grep for the
  fix identifiers); after building, verify the loaded extension actually
  contains your fix.
- Post-build symbol verification: a rebuild can succeed from stale sources or
  be silently undone afterward. Always confirm binary mtime > source mtime
  and md5-match repo bundle AND site-packages AND the ~/.duckdb cache (the
  cache serves stale binaries). Verify binary md5s at LAUNCH START, not just
  after rebuild — site-packages deployments do not persist across sibling
  sessions. Full four-point proof (review-10): mtime ordering, md5
  repo==site-packages, a distinctive string literal from the newest native
  code embedded in the binary, and which side of each parity test fails.
- ~108 of the historical "172/183 parity drift" failures were a stale
  COMMITTED binary, not lost source — before diagnosing lost fixes, rebuild
  from current source and re-run.
- Milestone-4 reconciliation result: parity 75→7 failed. Two re-land traps:
  (1) exact-ratio from-factor MUST come from convertQuantityToBase(1.0, unit)
  directly — the from_base quotient carries binary64 noise, and `%.1g`
  renders 1000 as "1e+03"; (2) unitless quantity-shaped JSON objects vs bare
  numbers compare EMPTY (§6.1.1) in the JSON comparator layer —
  fpValueAsQuantity REJECTS unitless objects, so the guard cannot live in the
  quantity layer.

## Most Reliable Bug-Finding Strategies

(distilled from FP-01..FP-20 + CQL-01..22 + SOF-VD-01..13; see Personality
Effectiveness for attribution and ARCHIVE_LOG for instances)

1. **Probe the spec's normative example lines verbatim** — highest-yield
   single technique of both campaigns (`9.9 / 3.0 // 3.3`, `12 'cm2' / 3 'cm'
   = 4 'cm'`).
2. **Probe through iteration functions** — error-vs-empty divergences are
   invisible at the UDF top level; feed them into all()/exists()/where()/
   select()/iif criteria.
3. **Check the sibling comparison surface** — equality works while ordering
   is empty (or `=` vs `~`, in vs included in) means different conversion
   surfaces; audit guard predicates, not just tables. Comparison lowerings
   must be audited in PAIRS.
4. **Aim at INTERSECTIONS of independently-clean surfaces** (EXPLORER):
   navigation × type operators; classifier × error taxonomy;
   literal-grammar × arithmetic-precision; feature × alternative spelling
   (backtick vs plain %`name`); magnitude × precision; operand-type ×
   boundary. Official fixtures never combine element-level constructs
   (where × forEach, forEachOrNull × unionAll, alternative spellings) —
   every SOF-VD-08 HIGH came from such cross-products.
5. **Walk EVERY table row and overload form** (HISTORIAN): arity is part of
   the signature; '{'-prefixed dispatch funnels are fragile.
6. **Differential corpus against ground truth, not spot probes** (FIX phase).
7. **Re-probe around each fix**; after a family-level fix, probe the CONSUMERS
   and COMPOSITIONS of the fixed operators, and the operand SHAPES the fix
   did not touch (alias-bound defines, retrieve aliases, alias-of-alias
   DEPTH, retrieve-shaped operands, derived selections); and audit the PRIOR
   fix's SCOPE (its bookkeeping may only cover one depth/branch).
8. **Read official fixtures BEFORE filing and BEFORE writing expectations.**
   Grep fixtures for BOTH spellings (infix AND function forms).
9. **Attack the META-surface on pre-hardened chunks** (fhirpath_is_valid
   classifier vs its own doctrine) — both engines can misclassify
   identically (parity-blind).
10. **Cross-chunk seams**: equality/ordering extensions must flow through
    membership/distinct/repeat-dedup unchanged.
11. **Spec-version + fixture dual-fetch**: N1 AND master HTML; official
    grammar artifacts (FHIRPath.g4, cql.g4) over prose recall; HL7 reference
    engine source (cqframework Kotlin evaluators) and the reference
    validator/implementation source (sof-js) to settle prose conflicts; the
    machine-readable artifact (SD XML / releases-branch zip) outranks HTML
    pages and mandate prose; where prose is disputed, RUN a generated ANTLR
    parser, don't just read.
12. **Verify probe harness assumptions before the code**: PYTHONPATH=repo
    (stale site-packages fabricates findings), register_fhirpath is True,
    fhirpath() returns LISTS of strings, population SQL via
    translate_library_to_population_sql (bare to_sql() SELECTs are harness
    artifacts), arity grammar, fixture XML namespaces.
13. **When a rule is fixed in one dispatch family, grep every OTHER family
    computing the same rule** (plain decimals fixed, Quantities forgotten;
    engine fixed, exported helper forgotten — 12+ documented helper
    instances; Python UDF fixed, native table forgotten — and vice versa).
14. **Run the SAME boundary battery in the other engine**, including the
    NO-PYTHON engine (native-loaded connections shadow native UDFs with
    Python supplements; _PYTHON_PREFERRED_CPP_CONFLICTS); chain converted
    values into downstream operators comparing exact display text.
15. **Probe equivalence invariants** when a spec defines one function as
    shorthand of another (repeat(children()) ≡ descendants();
    ConvertsToT accepts iff ToT converts; includes ≡ contains).
16. **Probe self-recursive metadata paths** (item, component) and DEEP
    multi-segment navigation chains over retrieve defines.
17. **Test error-in-subexpression contexts** (union operands, .count(), iif);
    cross-engine DIFF at scale — every DIFF is a bug.
18. **Probe rendering-regime TRANSITION boundaries** (fixed vs scientific,
    exact vs binary64 degrade) and values ADJACENT to integer/type
    boundaries (0.3 div 0.1; Long min/max; 2^31 internal scaling).
19. **Probe typed-null operands** (`null as Interval<T>`) through every
    operator dispatch; probe operands through PARTIAL FHIR data
    (birthDate '1975-03') and through NAMED DEFINES — literal batteries
    repeatedly missed every dynamic-path defect.
20. **Internal inconsistency is a bug oracle**: sibling operators/constructor
    arities disagreeing with each other proves one wrong regardless of spec
    ambiguity.
21. **Re-derive expected values from live normative text before logging** —
    probe-expectation errors outnumbered real bugs roughly 3:1 on clean
    chunks; when every case of a form returns the same value, suspect silent
    operator rewriting and dump the generated SQL.
22. **Read the emitted SQL for a multi-row define before running values** —
    the LOWERING SHAPE predicts wrong-value bugs (LEAST over LIMIT-1 can only
    see one row). Fetch the SQL result COLUMN TYPE, not just the value.
23. **Multi-patient fixtures hide cross-patient leaks** — verify per-patient
    isolation whenever CTEs/derived tables are involved.
24. **Bisect before logging** (git-stash or hunk-level causality tests) to
    separate pre-existing failures from regressions; a clean revert requires
    exact block replacement, not hand-patched control flow.
25. **DQM gate before closing**: spec-strict fixes that regress DQM by one
    patient mean fixtures pin the other behavior (fixtures outrank prose);
    diff the generated SQL between fix and revert to find the flipped
    comparison, then scope the spec rule.
26. **Verify binarity fresh through behavior** (fresh LOAD / no-python
    connection), never through build exit codes; check binary md5 at launch
    start.
27. **Push result VALUES to pathological size, not just input shapes** —
    the orjson ~127-level dumps ceiling only surfaces when a column RETURNS
    deep JSON; compare OUTPUT TYPES across input paths.
28. **When a spec publishes a formal algorithm (Process(S,N))**, derive
    expectations from it, not from intuition or fixture coverage; apparent
    composition bugs are usually your model being wrong.

## NOT A BUG / INTENDED Doctrine Registry

Later launches MUST NOT re-file these without a new fixture/spec mandate:

### Fixtures outrank prose (standing doctrine)

- Official fixtures outrank spec prose AND engine parity in BOTH directions;
  a missing `<output>` in fixture XML is an expected-EMPTY assertion, never
  "unspecified". A prose-conformant fix that regresses fixtures gets
  REVERTED at the Recovery Gate (FP-15 subtype, CQL-06 ToTime tz, CQL-08
  query-null, CQL-09 quantity promotion, CQL-10 HighBoundary, CQL-17
  width/size exactness).
- CQL-19 pins: list union with a null operand returns the OTHER list
  (cqframework/clinical_quality_language#887; 2019May prose stale);
  `null properly included in {list}` is FALSE per fixtures contradicting the
  prose example.
- CQL-06 pin: ToTime accepts tz-offset strings (ToTime2/3/4); ToTime
  normalizes the offset away (@T14:30:00.0+05:30 → @T14:30:00.000).
- CQL-16 pin: quantity successor steps by Decimal 1e-8 — runtime quantity
  JSON is always float; _parse_quantity deliberately erases authored
  int-ness (supersedes the 2026-07-02 followup).
- CQL-17 pin: width/size compute EXACT values beyond the point-type range
  (Long MIN..MAX exact-value doctrine) — no overflow-null.
- CQL-20 pins: AllTrue(null)→true, AnyTrue(null)→false, Count(null)→0;
  iif is FHIRPath not CQL (CQL-06 doctrine).
- CQL-04/08 pin: population-SQL Boolean define surface collapses null→FALSE
  (measure membership semantics; row-presence boolean-CTE invariant);
  expression-level 3VL preserved (null implies null → null per Table 9-A1).
- CQL-08 pin: query-valued `is (not) null` is EXISTENTIAL in official eCQM
  content — literal-list path stays strict-spec; both pinned by test.
- FP-06 pin: spec `invalid="execution"` fixtures beat older repo pins.
- FP-01 pin: -0.0034.highBoundary(1) → 0.0 per fixture.

### ViewDefinition adjudications (load-bearing for Analytics Layer)

- Sibling selects CROSS JOIN (IG notes / Process(S,N) 'parts'), NOT UNION; an
  empty nested-select part suppresses ALL rows for that focus. Never
  order-assert across union branches.
- unionAll arm model: branch rows = enclosing columns + branch columns, no
  standalone base row; UNION ALL preserves duplicates; branch mismatch
  raises at GENERATION (spec requires only "an error"); column-empty
  branches emit NULL rows (distinct from row suppression); collection=true
  branches with BOTH types unset pass (sof-js compares names only).
- Value-dedup: repeat/union dedups by value (`=`) — identical siblings
  collapse; O(n²) on deep trees is inherent; row order unpinned (%rowIndex
  is the stable position); primitive-yielding repeat paths empty (dict-only
  traversal).
- select.where is an EXTENSION doctrine: SD 2.0.0 has NO select.where
  (root-only; sof-js drops it on forEach selects) — fhir4ds per-focus
  select.where is intentionally retained superset behavior. Where semantics:
  collection-boolean results EXCLUDE per FHIRPath singleton-true; exclusion
  via exact `fhirpath_json(...)='[true]'`.
- spec_tests NO-DRIFT doctrine: authoritative suite is the sql-on-fhir.js
  snapshot (byte md5 via gh API on FHIR/sql-on-fhir.js HEAD); IG-clone
  /tests/*.json are STALE DRAFT fixtures; local /mnt/d/sql-on-fhir-v2 is a
  STALE 2024 fork. Forward drift (upstream HEAD → v3.0.0-ballot examples)
  is correctly rejected by the 2.0.0 parser.
- cnl-1 on ViewDefinition.url is WARNING severity (official SD XML; demoted
  from ERROR in SOF-VD-13 HISTORIAN); profile[]/meta.profile[] use
  permissive canonical check (|version OK) while url is strict; Column.type
  keeps permissive URI check (cnl-1 not applied); cnl-0 name warning
  implemented as first-char+length (equivalent under the sql-name charset
  precondition); generate_view_sql intentionally swallows warnings —
  validate_view_definition() is the capture API (matches sof-js).
- Shareable/Tabular canonicals: recognition MUST use the published
  http://hl7.org/fhir/uv/sql-on-fhir/... URLs (data-driven alias frozensets
  in viewdef/metadata.py); enforcement at ALL nesting depths; versioned
  meta.profile canonicals recognized; foreign unknown canonicals ignored +
  retained (sof-js never inspects meta.profile); plain VD without status
  parses (official validator outranks prose) while profiled VDs enforce
  required status/url/name/fhirVersion/Column.type; full-URI Column.type
  normalized to primitive name.
- SOF-VD-01 pins: FHIR `uri` regex is officially `\S*`; 39 legacy resource
  codes are an intentional cross-version superset — do not prune; fhirVersion
  ValueSet is UNFILTERED (full codesystem expansion; REV-013's 63 codes).
- SOF-VD-02 pins: constants substituted TEXTUALLY — every numeric
  serialization into FHIRPath must satisfy the literal grammar (no exponent;
  parse_float=Decimal; int32 literal range); list-valued %constants
  inexpressible per SD; constants named after builtins never substituted
  (spec-silent); builtin-vs-constant precedence matches RI Object.assign
  (envVars-wins) order.
- SOF-VD-04 pins: whitespace-only tag.name/value allowed (validate_tag_string
  — do not borrow FHIRPath whitespace doctrine); tags validated but never
  consumed; collection=true emits DuckDB LIST (empty list for absent; JSON
  strings for non-primitive); column type must match the FHIR primitive at
  runtime.
- SOF-VD-05 pins: no user-facing contentReference in any v2 version
  (select.select recursion only); forEachOrNull null rows have SQL NULL child
  outputs (not empty arrays); %rowIndex binds 0 on preserved null rows.
- SOF-VD-06 pins: forEach errors degrade uniformly to empty (0 rows / one
  null-preserved row); duplicate forEach JSON keys last-wins; JSON-null array
  elements excluded from collections (%rowIndex counts the filtered
  collection); %parent is not a builtin.
- SOF-VD-09/10 pins: unknown constant fields accepted (no
  additionalProperties:false on constant items); valueInteger 3.0 rejected
  (FHIR integer forbids decimal point); sql-name has no length cap; plain
  ValueError at direct-dataclass __post_init__ (SQLOnFHIRError subclasses
  ValueError); 3.0.0-ballot-only fields accepted + preserved (no ballot
  invariants in 2.0.0 scope).

### FHIRPath doctrine

- Mixed calendar-vs-UCUM year/month equality (`1 year = 1 'a'`) returns
  EMPTY; calendar-vs-definite-time dimension mismatch → null for =,<,!= and
  false for ~,!~.
- Date/DateTime-vs-plain-string equality coercion is a documented shared
  JSON-convenience convention; Time-literal vs plain String IS empty (§5.5
  Explicit-only).
- Time values render T-less everywhere; §6.7 partial-time truncation
  (`@T14 + 30 'minutes'` → `14`) is correct.
- `t is Boolean` → false family: FHIR-vs-System namespace split
  (testType11–14). `{}.iif(true,...)` returns the then-branch (testIif7).
- `ofType(System.String)` never matches FHIR strings; primitives are
  independent types (`id.ofType(FHIR.string)` empty is correct).
- Dotted `X.and(Y)`/`or`/`xor` INVALID grammar (infix keywords); `.not()` IS
  a function. Non-Boolean singletons are TRUTHY (`(0).not() = false`).
- is/as ASYMMETRY: `is` subtype, `as`/`ofType` EXACT — fixtures outrank
  2018Sep §6.3 prose. Chained is/as left-associative and valid.
- `|` union dedups with `=` at construction; `1 = 1 '1'` true.
- `tail()` zero-arg; wrong arity = invalid, distinct from wrong-TYPE args
  (valid execution errors). `skip(1)` on empty focus is valid.
- Execution type errors classify is_valid=True; spec-mandated empties
  (temporal precision, calendar-vs-UCUM y/m, offset temps, incompatible
  quantity dims) stay empty.
- defineVariable reference syntax is `%name` (spec-ballot `$name` rejected);
  `%` is not a FHIRPath operator (`mod` is).
- One-arg aggregate $total starts EMPTY; `$total.sum()` is a CQL-ism.
- @2018Z / @T12:30Z rejected = documented FHIR-datetime-strict policy
  (FP-06/CQL-11 doctrine).
- Tuple literals `{a:1}` and literal lists `{1,2}` NOT in the grammar —
  rejection is conformant (2018Sep AND N1).
- %context = ORIGINAL node; %resource/%rootResource track the ORIGINAL
  node's container; type() returns {namespace,name} only.
- Chained implies LEFT-associative (official ANTLR grammar).
- `~` string whitespace normalization = {tab, space, LF, CR} only.
- `convertsToInteger('2147483648')` → false (32-bit doctrine); `'5L'`
  accepted by toDecimal; 1-arg to* forms take a FORMAT argument;
  dateTime-shaped strings accepted by `toDate()`.
- `1 'cm' ~ 1 's'` empty (incomparable-quantity doctrine);
  `toQuantity('')` acts as no-arg form.
- Physical SQL row order after repeat filters is not a conformance signal;
  `%rowIndex` is the stable traversal position.

### CQL doctrine

- CQL-21: empty-system Code source treated as wildcard by `in_valueset`
  (load-bearing for the String overload); timezone-offset birthDates use
  day-precision treatment of invalid timestamps.
- CQL-22: Message `code` slot accepts any scalar token (§13.1); >5-arg
  raises; informational channel unimplemented by design in
  translate-to-SQL.
- CQL-05: `As is not a conversion`; Children({1,2,3}) → 0; no Code/Concept
  ToString overload.
- CQL-08: IsTrue/IsFalse(non-Boolean) → false (no truthiness).
- CQL-03: E-notation literals/ToQuantity rejected (grammar has no
  exponent); ToString(Ratio) trailing `.0` formatting pinned.
- CQL-12: Split/SplitOnMatches keep trailing empty strings (spec-silent,
  engines agree); ReplaceMatches '$1' over a groupless pattern raises typed
  CQLRegexPatternRejected (Java-consistent).
- CQL-09 spec-erratum pin: ListNotEqualIsNull /
  DateTimeWithMillisecondsEqualIsNull contradict the algorithm text; the
  implementation follows the algorithm.
- CQL-10: GeometricMean has NO Quantity overload; GeometricMean(negatives)
  → null (ln convention); Min/Max Quantity returns element in its own unit;
  cm*cm→cm2.
- CQL-14: `same X as Interval[...]` with a qualifier is singleton semantics
  — do not "fix" to start-only.
- CQL-16: reference overlaps before/after is start-based strict;
  Interval[null,null] overlaps → null; `meets <prec> before` is not valid
  grammar; intersect with null low keeps the finite low.
- Singleton-from >1 on query-shaped sources stays NULL (fixtures/DQM
  outrank the prose run-time error; element-exact paths keep the typed
  error) — CQL-19 pin.
- `O.component.code.code` is invalid FHIRPath (CodeableConcept has no
  `code` child) — empty is spec-correct (CQL-18).
- CQL-01: >extent Decimal literals ≤28 int digits are fixture-pinned VALID;
  ConvertsToBoolean('yes')=true (Table 9-F); convert 1.9→Integer null is
  CORRECT (no such conversion).

## Recurring Architectural Patterns

- **Dual-engine parity doctrine**: every FHIRPath/CQL semantic change lands
  in BOTH the Python fallback and native in lockstep, with canonical
  spellings so parity tests don't chase phantom diffs. Changes at
  comparison/consumer sites keep shared tables (`ucum_units.hpp`)
  byte-identical ("shared-table ≠ defer"). Parity is necessary, not
  sufficient — engines have agreed on wrong values repeatedly.
- **Exact Decimal string arithmetic**: native quantity/decimal math uses a
  Decimal string module mirroring Python `decimal` (28-sig ROUND_HALF_EVEN,
  29-digit guard digit). §6.6.2 division ALWAYS Decimal. round() is
  TRADITIONAL; transcendentals binary64 shortest-round-trip. Never transit
  DuckDB's DOUBLE `/` with exact Decimal operands; emit fixed notation for
  small magnitudes (VARCHAR→DECIMAL casts round scientific text UP).
- **Calendar quantity canonicalization**: quoted keyword units canonicalize
  to bare form; §5.5.7 factors month-based year↔month, day-based
  cross-group; week/day/time keyword-vs-UCUM ordering exempted,
  year/month-vs-'a'/'mo' stays empty.
- **UCUM exponent algebra / unit-space composition**: term-expression
  parse/render/reduce; derived units curated + recursive base expansion;
  mixed-unit +/- yields most-granular input unit (N1 §6.6.3). Known gaps:
  Pa own-dimension; derived/prefixed families (kN) empty.
- **Error-message contract coupling**: new type-error messages must update
  BOTH `_is_valid_empty_result_error` (udf.py) and native
  `FhirpathIsValidFunction` acceptance lists (13+ instances).
- **Metadata triple-maintenance (REV-005 family)**: FHIR type metadata in
  evaluator.cpp fhirFieldType, models/r4 JSON tables, and fhir_model.py —
  every field-type change updates ALL copies; prefer suffix keys when native
  lacks paths. Long-term: generate native tables from metadata.
- **Definition shape metadata**: CTE defines have two physical list shapes
  (stored-list value vs element-rows) sharing the same inferred type —
  explicit DefinitionMeta discriminators (stores_list_value, RowShape) are
  required; containment flags like has_resource conflate shapes. See
  REV-010 for the consolidation debt.
- **DuckDB engine constraints are design constraints, not fights**: no macro
  recursion, no correlated UNNEST, no subqueries in lambda bodies, TRY()
  can't wrap volatile fns or scalar subqueries, macro CASE type-guards don't
  protect lambdas, Python UDFs can't be signature-overloaded, COALESCE
  binder is order-sensitive to mixed types, DECIMAL→DOUBLE casts inside
  var_samp/median.
- **Spec-owning dataclasses enforce invariants in `__post_init__` uniformly**
  (Column, ColumnTag, Constant, Join); Select/ViewDefinition remain
  DEFERRED per Minimal Footprint. Public API wrappers preserve typed
  exceptions (`SQLOnFHIRError` inherits ValueError); never
  `except Exception: raise ValueError`.
- **Reserved runtime variables win over user constants** at BOTH validator
  and resolver boundaries (`FHIRPATH_BUILTIN_VARIABLES`); required string
  fields reject semantically-empty values.
- **Loader performance = amortization discipline**: fold per-resource checks
  into existing loops; standalone loops show as T/ratio > 1.10.
- **Model knowledge is data-driven**: is/as/type() operate via metadata
  (path2Type.json is the truth source), never lexical shape-sniffing;
  FHIRSchemaRegistry cardinality (not hardcoding) drives multi-valued
  navigation aggregation.
- **Delegate-to-engine pattern**: exported helper functions (functions/*.py)
  must delegate to engine FP_* implementations — reimplementation is the
  root cause of the 12-instance helper-forgotten family.
- **PYTHONPATH probe rule**: `python3 .temp/qa/x/probe.py` imports the STALE
  site-packages fhir4ds — always `PYTHONPATH=<repo>`; run the master gate
  with PYTHONPATH=repo explicitly.

## Recent FHIRPath Lessons

- R4 has NO dateTime-derived primitives — `instant` is a sibling of
  `dateTime`; `models/r4/path2Type.json` (7,705 entries) is the complete
  truth source for resource-qualified metadata.
- Native parser-specialized invocation nodes (e.g. `exists()` →
  `NodeType::ExistsCall`) bypass generic evalFunction validation — need
  local guards in addition to central arity checks.
- Python `re` `$` matches before one trailing newline — use `\Z` anchors
  wherever regexes validate FHIRPath literals.
- evaluator.cpp contains a literal NUL byte in a comment (~offset 33139);
  grep/file treat it as binary.
- Execute raw generated SQL before blaming the generator (the conformance
  harness adapter itself caused a phantom repeat failure).
- Antlr regeneration must use `-visitor` or 41 accept() methods silently
  vanish.

## Recent CQL Lessons

- Interval-derived scalars must drive point-kind-aware dispatch in EVERY
  consumer; `_is_cql_date_expression`'s blanket start-of/end-of match
  silently temporalizes numeric intervals.
- CQL-authored `Interval<DateTime>` parameter defaults must stay structured
  (low/high + closure flags); flattening lets population SQL include
  encounters outside a half-open high edge.
- Static-extractor helpers must recurse into ListExpression for
  collection-typed tuple fields.
- CQL aggregate/list/interval fixes are sensitive to SQL transport shape;
  clinical/Quantity/interval equality must not degrade to raw JSON equality.
- Fluent `X.distinct()` and function-form `distinct X` dispatch to the same
  order-preserving, NULL-retaining macro (`"Distinct"`), never
  ARRAY_DISTINCT.
- New CQL aggregate keywords must be registered in EVERY registry
  (pre-translate tuple + name maps + dispatchers) or they silently leak raw
  SQL; new JSON-array-string UDF names must be added to every translator
  recognition site (a missing site silently downgrades list_sum → SQL SUM).
- Sub-day Difference counts boundaries (§8.7), never reuses Duration
  truncation; C++ epoch-millis needs floor division pre-1970.
- A numeric→scalar-or-interval VARCHAR type change must be audited against
  EVERY generic SQL consumer (in-list, unary minus, GREATEST/LEAST, list
  aggregates, interval-in both bound branches).
- hunk-level bisect beats file-level attribution (QA-103: a single dropped
  `add_alias(table_alias=...)` registration was the sole DQM trigger);
  `resolve_placeholders` must traverse every SQLSelect child (order_by was
  missed).

## Recent ViewDefinition Lessons (consolidated SOF-VD-01..13)

- SOF-VD-01: `from_dict` preserves typed exceptions; binding code sets
  (fhirVersion, resource-types) are drift-prone — refresh from
  sushi-config.yaml-determined editions; value-set drift is bidirectional.
- SOF-VD-02: singular `constant` field; rejects legacy `constants`,
  duplicates, undefined `%name` (see literal-grammar pins above).
- SOF-VD-03: processing_model.md is the normative row-multiplicity algorithm
  (empty-part suppression; unionAll per-focus, ordered last); column paths
  are FOCUS-relative.
- SOF-VD-04: parser rejects plural `tags`; mutable `ColumnTag` revalidated
  at serialization/generation; collection defaults `False`.
- SOF-VD-05: recursive `Select.to_dict()` where-validation.
- SOF-VD-06/07/08: present JSON null for optional iterator fields rejected;
  present-empty `repeat: []` / `unionAll: []` rejected; wrapper-instance
  null-row suppression identity (`_union_origin_id`) with ids collected at
  the emission site.
- SOF-VD-09: root `to_dict()` validates root `where` via shared
  `validate_where_conditions()`; prefix-mixed-focus guard
  (`_prefix_tail_has_focus_operand`) raises loud in both orderings.
- SOF-VD-10: strict parser preserves absent-vs-present-null for root
  metadata; permissive validator warns for binding/sql-name violations;
  typed ParseError at the deep-nesting boundary.
- SOF-VD-11: native JSON numeric member access preserves raw number text;
  `%rowIndex` with `type: "integer"` emits DuckDB INTEGER;
  `_json_serialize` falls back to `_json_serialize_iterative` past the
  orjson nesting ceiling; multi-resource tables resourceType-filtered;
  materialized views keep catalog VARCHAR for temporal columns.
- SOF-VD-12: `to_dict()` calls the shared supported-profile validator.
- SOF-VD-13: extra_fields repr=False/compare=False (excluded from repr/==,
  byte-identical round-trip); sql-name enforced on name/Column.name/
  Constant.name; tag namespace warning only without '/'.
- Per-chunk issue counts: SOF-VD-01:3, 02:5, 03:3, 04:4, 05:1, 06:1, 07:1,
  08:1, 09:1, 10:3, 11:3, 12:2, 13:3 (all closed; archives hold detail).

## Personality Effectiveness

Launch highlight (SOF-SQ-01, SKEPTIC): mandate prose again diverged from the
machine-readable spec (invented canonical hosts, wrong type code, wrong
parameter cardinality). Winning move: locate the newest upstream git branch
carrying the profile FSH (upstream/sqlquery-view-sources, not upstream/sqlquery)
and derive everything from library-profiles.fsh + terminology.fsh +
sushi-config.yaml. Pattern now 3-for-3 with SOF-VD-12: ALWAYS verify canonicals
and code bindings against sushi-config.yaml canonical + FSH before trusting
mandate text.

Launch highlight (SOF-SQ-01 3rd, EXPLORER): after SKEPTIC+HISTORIAN hardening,
a full adversarial volume/edge battery found zero actionable defects — the
chunk is stable. Notable confirmations: first-bad-entry error precedence with
indices at 100-entry volume; BOM'd unicode SQL round-trips byte-exact;
duplicate parameter names are spec-legal; relatedArtifact label may collide
with parameter names; SQLView tolerates `parameter: []` (0..0 counts
elements). Deferred QA-003: runner `select_best_content` is exact-match on
dialect strings, so `application/sql;charset=...` passes the invariant but
dies at execution with UnsupportedDialectError — fine per extensible binding.

Role summaries first; recent per-launch highlights after.

Launch highlight (SOF-SQ-01 2nd, HISTORIAN): the SKEPTIC's to_dict 'roundtrip
fixed' claim was only half true — extras at the TOP level survived, but every
known-but-unmodeled FHIR field and all per-entry extras (sqlText extension,
relatedArtifact.display, parameter.documentation) plus meta/type verbatim
identity were silently dropped, and the official canonical was rewritten to
the legacy spelling. Lesson: for roundtrip claims, test a FULLY-populated
resource, and diff key-by-key, not just the fields the fix touched. Route EXPLORER
last so its intersection probes confirm earlier-personality fixes at
boundary cross-products.

- **SKEPTIC** — best for direct-boundary/malformed-shape attacks: malformed
  arity, present-null/present-empty fields, plural aliases, representation
  canonicalization, cross-engine comparison semantics, grammar-source
  reading (FHIRPath.g4 / cql.g4 lexical fragments and alternative ORDERING),
  spec-example-first probing, diffing the official validator schema
  (additionalProperties:false / minItems:1 mining heuristic paid off
  repeatedly). For CQL: probe EXECUTION with registered macros, not
  translate-only; read the local spec source repo rather than code-comment
  citations. Verify canonical identifiers / codeset expansions against the
  primary source before testing enforcement. Blind spots: declaring a native
  display correct without fixtures; DEFERRED on "shared table" grounds
  without checking consumer-site workarounds; overall arity while validating
  per-slot types; spec clarifying clauses beyond the signature line;
  reading severity/structure from HTML pages instead of machine-readable SD
  XML. Environment traps: background builds racing source edits; stale
  cached extensions; probe harness passing None as resource; namespaced
  fixture XML.
- **HISTORIAN** — strongest for official-model parity and regression
  assurance: every table row/overload form, formal cardinalities, fixture
  grounding, dual-version spec fetching (N1 AND master), chasing a spec
  phrase to its DEFINITION section, re-running the section's own inline
  examples, verifying SURPRISING behaviors against primary sources
  (reference engine Kotlin, sof-js validate.js), reading the PRIOR launch's
  architect residual-drift notes (promote architect LOW observations to
  probe hypotheses), re-verifying prior launches' spec claims live (refuted
  an entire landed CQL-07 "fix"; overturned a prior SKEPTIC
  "intentional-strictness" pin via the SD XML severity field), and the
  fix-complement: after a fix, audit its SCOPE (the dimension the fix's
  bookkeeping didn't cover — usually DEPTH) and probe operand shapes and
  consumers the fix did not rewrite. When a chunk receives multiple
  personalities, HISTORIAN's clean walkthrough is the robustness-
  confirmation pass. Pin the canonical v2 artifact from the GitHub
  `releases` branch (live CI serves v3.0.0-ballot). Blind spot: reading a
  missing `<output>` as "unspecified" instead of expected-empty.
- **EXPLORER** — strongest for composed behavior and pathological inputs:
  INTERSECTIONS of independently-clean surfaces, DEGENERATE forms, operator
  × operand-SHAPE matrices, compose operators with THEMSELVES,
  error-in-subexpression contexts, convert→convert round-trips,
  self-recursive metadata paths, rendering-regime transitions, scale/depth
  stacking, result-VALUE pathology (deep/large returns), combined-profile
  and alternative-spelling pressure. Confirmation role: verifies earlier
  fixes hold under boundary cross-products; zero-findings EXPLORER closes
  are cheap insurance. For CQL: compose DEFINES through
  translate_library_to_population_sql. Cost notes: read official fixtures
  BEFORE writing expectations; normalize boolean output case; verify own
  arithmetic expectations before logging; suspect the probe's resource
  builder before bisecting engines.
- **ARCHAEOLOGIST** — stress-composing covered semantics; performance/scale
  probes (linearity, leak).
- **SPECIALIST** — systematic measurement anchored on the Key Question;
  amortization discipline verified no hot-path cost.
- Common probe traps: probe-authoring errors outnumber real bugs on clean
  chunks — confirm with a direct single-expression rerun before filing;
  JSON outputs need normalization-aware expectations; bind a real resource;
  re-run old .temp probes before trusting them; isolate unexpected NULLs
  against a minimal resource that HAS the field; verify probe harness shape
  (population SQL, registered helpers) before trusting empty results.
- Institutional-memory payoffs (recurring): doctrine pins told us which
  'BAD' expectations were ours; the CQL-05 'As is not a conversion'
  adjudication killed a false positive instantly; bisect-attribution
  separated pre-existing failures in minutes; re-applying the ARCHIVE's
  highest-yield lesson verbatim (CQL-16 mixed point types → CQL-17 finds).
  Memory also cuts both ways: archived gate claims can be stale — rerun the
  master gate yourself; a confirmation pass that re-checks the same subset
  as a fix inherits the fix's blind spot — probe the complement.
- Saturation signal: when a chunk's operator core + contexts are verified
  clean across engines by two personalities, the marginal value of a third
  launch is low; budget favors unprobed contexts over re-testing the core.

### Recent per-launch highlights (full narratives in spec_comp/ archives)

Distilled SOF-VD lessons not already in the strategy list:

- Verify mandate-cited fields and invariant SEVERITIES against the SD
  element list / SD XML severity field before testing enforcement; the
  machine-readable artifact outranks mandates and HTML pages; re-adjudicate
  prior "intentional strictness" pins against primary artifacts.
- After ERROR→WARNING demotion, re-run the adversarial matrix on the NEW
  warning path; audit warning predicates against spec character classes
  (ASCII vs unicode-loose Python); probe the object-construction path, not
  just JSON parsing.
- Hard-coded external identifiers (canonical URLs, OIDs, codesets): fetch
  the authoritative artifact and string-compare; upstream git history
  settles provenance; a codeset fix must match the FULL expansion.
- Serialize the round-trip (json.dumps of to_dict() is a distinct assertion
  from dict equality); compare OUTPUT TYPES across input paths.
- Probe the DEPLOYMENT surface (views, catalogs, sessions), the TEST
  RUNNER, and the load path — not just query results. A gate "failing" at
  100% pass-rate means check report FRESHNESS (mtime + log_run entry).
- Attack the SYMMETRY of existing guards (one ordering loud, reversed
  returns data → silent misroute) and the SCOPE of prior fixes (the
  un-audited dimension is usually DEPTH); collect bookkeeping ids AT the
  emission site so misalignment is structurally impossible.
- Mandate-item × syntax-spelling cross-products (backtick vs plain %`name`);
  a released-SD re-download converted a suspected bug into a doctrine
  confirmation.
- Extreme-depth harness traps: stdlib json recurses before the UDF — build
  fixtures by string concat, assert via _json_serialize_iterative; load the
  bundled binary directly (allow_unsigned_extensions LOAD) to exercise
  native; segfaults are signal — chase with faulthandler; deep probes are
  TIME-bound on WSL/drvfs.
- When rows go missing, bisect downward (view SQL → UDF → core evaluate)
  with a per-element SHAPE table; assert provenance flags, not data shapes.
- When neither spec nor fixtures pin a behavior, dual-engine agreement +
  upstream-removal evidence suffices for INTENDED; when a mandate asks for
  behavior the grammar cannot express, verify inexpressibility against the
  SD; fetch the formal Process(S,N) algorithm BEFORE judging outputs.

## Validation Notes

- For ViewDefinition changes, run fresh probes first, then focused
  parser/generator/DuckDB pytest, ViewDefinition conformance, and finally
  full conformance (2832/2832).
- For DuckDB-backed CQL/FHIRPath changes, keep forced Python fallback,
  native-loaded registration, and no-Python C++ surfaces aligned where all
  exist; rebuild + redeploy after evaluator.cpp/cql_extension.cpp changes;
  run the FULL package pytest tree during fix verification (surfaces
  independent bugs), plus chunk-scoped legacy integration files.
- Standard final gate:
  `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`.
- Run the conformance suite BEFORE handoff, not after (FP-15-h Recovery Gate
  lesson). Run the DQM suite after ANY shared type-inference edit.
- DQM gate reports can be STALE after infra flakes (SOF-VD-11 EXPLORER) —
  check mtime + log_run entries; prefer final-tree re-verification over
  per-chunk gate claims.

## Milestone Review Summaries

- Milestone reviews 5–50 (through 2026-06-09): clean passes, 0 open issues
  at each checkpoint; review-50 closed REV-045-001/002.
- #1 (FP-01..05): CLEAN; three hardening findings filed (stoi throw,
  metadata duplication, staging hygiene).
- #2 (FP-06..10): CLEAN of C/H; REV-004 widened; 2 new LOW.
- #3 (FP-11..15): CLEAN; extension binary verified newer than sources.
- #4 (2026-08-19 parity drift diagnosis + reconciliation): see
  Sibling-Session Clobber Hazard — resolved 75→7 failed.
- #5 (CQL-01..05) / #6 (CQL-06..10): clean; clobber-hazard symbol audit
  across FP-11..20 and CQL-01..10: all present. Operational: git diff/status
  can hang on the drvfs working tree — scope diffs to subdirectories with
  timeouts, or fall back to symbol greps.
- #7 (CQL-11..15): site-packages cql binary lagged the final rebuild by one
  iteration — md5-check all three locations every review; some native fixes
  only exercise under no-python runtime tests (_PYTHON_PREFERRED_CPP_CONFLICTS).
- #8 (CQL-16..20): deployment clean; REV-010 opened (RowShape accretion);
  the three mid-period DQM regressions were each a new carve-out interacting
  with an old one.
- #9 (CQL-21..22 + SOF-VD-01..03, 2026-08-23): deployment clean (cql
  c5b22d58, fhirpath 57d0634b); live native smoke of cqlUncertain*
  confirmed three-valued semantics; REV-012/013 opened; ViewDef chunks
  clean (860 unit + 144 conformance); DQM 47/47 2nd consecutive green.
- #10 (2026-08-23, 50 chunks; delta SOF-VD-04..08 + CQL-22): CLEAN.
  Disproved the "fhirpath sources ahead of binary" claim via the four-point
  binary proof (see Clobber Hazard). Opened REV-014/015/016. No fhirpath
  rebuild needed before campaign end.
- #11 / review-55 (2026-08-24, 55 chunks; delta SOF-VD-09..13): CLEAN.
  Gates: viewdef pytest 1241, ViewDef 144/144, DQM 47/47 (4th consecutive
  green). Binary freshness holds (cql c5b22d58, fhirpath 57d0634b,
  repo==site-packages). REV-009 downgraded TERMINAL-UNCONFIRMED.
  REV-014/015 re-verified live (same 7 residual parity failures, no new
  regressions). ViewDefinition section (13/13 chunks) release-ready;
  layering coherent (parser/types/constants/generator/metadata, no
  reach-throughs).

## Analytics Layer Watch-Items (from review-55, for SOF-SQ-01..03)

- Extend `generator.py` rather than forking SQL emission into a new module.
- Quote identifiers and literals in any new outer-query layer.
- Route new serialization through `_json_serialize` /
  `_json_serialize_iterative` and `_run_with_recursion_budget` — never raw
  json/orjson at depth.
- Reuse `constants.py` literal grammar for any generated constants/literals.
- Keep model knowledge data-driven (no resource-type branches in generic
  logic).
- Do NOT release `expanded_selects` early — it breaks unionAll null-row
  identity (the wrapper-instance suppression doctrine, SOF-VD-08).

## Personality Effectiveness addendum (SOF-SQ-02, SKEPTIC)
Winning move: read the coercion boundary first, then test whether the computed type is ever APPLIED, not just whether wrong types error. The runner passed every error-message test while silently binding temporal params as VARCHAR — the mandate's 'registry correctness' clause (type actually reaches DuckDB) exposed what error-shape tests could not. Also: verifying a fix (partial FHIR date '2020') immediately surfaced a spec-valid input the fix broke — always re-probe spec-valid edges after tightening validation.

## Personality Effectiveness addendum (SOF-SQ-02 2nd, HISTORIAN)
Winning move: re-test a fixed defect class on a DIFFERENT input axis. The SKEPTIC closed the string-value coercion hole; the HISTORIAN found the identical hole for Python-native values (`datetime.time` for declared date bound verbatim) because the guard was `if not isinstance(value, str): return value` — value-KIND blindness mirrored the earlier type-application gap. Also decisive: re-deriving spec ground truth BEFORE judging probe anomalies — 'materialization vs inlining ... implementation decisions' language converted 4 suspicious probe results (silent view overwrite, table-collision error, dangling views after mid-chain failure, raw DuckDB errors for undeclared placeholders) into NOT-A-BUG registry entries instead of false positives. Probe-expectation errors still outnumber real bugs; adjudicate against the newest upstream branch text first.

## Personality Effectiveness addendum (SOF-SQ-02 3rd, EXPLORER)
Winning move: execute the spec's OWN example fixtures, not just self-authored bodies. Both HIGHs came from reading upstream example FSH/notes first (`:city` placeholder convention) and only then probing — the runner had 94 passing tests yet could not run the canonical spec example. Second winner: same-instant different-spelling equivalence probes (string vs native datetime) expose host-environment-dependent nondeterminism that single-value tests never see. Adjudications: positional/mixed `?` bodies and duckdb's str-returning CAST('24:00:00' AS TIME) stay INTENDED (engine-boundary).

## Evolution Statistics row (SOF-SQ-03, 2026-08-24)
| SOF-SQ-03 Analytics Layer integration seams | SKEPTIC | 2 H/2 M fixed | Final chunk: chains/cycle/transitivity/one-way dep all passed, but integration seams leaked — parsed SQLQuery/SQLView resolver returns rejected, duckdb exceptions from CREATE VIEW escaped the typed hierarchy entirely, ambiguous Library/VD dicts misrouted, parameter.name unvalidated. Fixes in runner `_resolve_view_sql` + validator. sqlquery 102→109; master gate 2832/2832. |

## Personality Effectiveness addendum (SOF-SQ-03, SKEPTIC)
Winning move: audit the exception paths, not just the happy paths — wrap-probe by feeding each documented resolver return shape and each failure mode (bad base64, unparseable VD, invalid generated SQL) and check the EXCEPTION TYPE that escapes. Typed-error wrapping was 1-of-4 correct: only the resolver-call itself was wrapped; everything downstream leaked (worst: raw _duckdb.BinderException, outside SQLOnFHIRError entirely). Second lesson: docstring contracts (DependencyResolver 'returns SQLQuery or SQLView') are testable spec — the code path rejecting them was a HIGH the type-hierarchy tests alone would never find.

## Evolution Statistics row (SOF-SQ-03 2nd, 2026-08-24)
| SOF-SQ-03 Analytics Layer integration seams | HISTORIAN | 2 L (1 fixed, 1 intended) | Post-SKEPTIC tree re-verified regression-free on all 4 fixes (incl. subclass isinstance, nested two-level error context) and all mandated items; new probes (mixed resolver shapes in one list, round-trip byte-stability, native/fallback parity, placeholder/dialect edges) found only a docstring contract understatement (fixed) and the main-body-raw-engine-error observation (INTENDED, threat model). sqlquery 109→113; gate 2832/2832. CLEAN exit at iter 1. |

## Personality Effectiveness addendum (SOF-SQ-03, HISTORIAN)
Winning move: regression-probe the SEAMS of the prior launch's fixes rather than re-running its probes — combining every resolver return shape in ONE dependency list, subclass instances, and two-level nested failures exercised the SKEPTIC's isinstance and error-wrapping carve-outs harder than their original tests, and all held. Remaining finds were contract-documentation drift (docstring understating the fixed resolver contract) — after two hardening launches, docstring-vs-alias drift is what survives. Lesson: when a fix changes an accepted-input contract, grep the adjacent docstrings in the same commit.

## Evolution Statistics row (SOF-SQ-03 3rd/final, 2026-08-24)
| SOF-SQ-03 Analytics Layer integration seams | EXPLORER | 0 fixed / 1 L INTENDED | CLEAN. Campaign-final boundary sweep on real DuckDB: diamond graphs (per-edge re-materialization idempotent, rows correct), depth-5 mixed chain, dep-view+param composition, label==source-table (typed Catalog error, table not clobbered), params-do-NOT-flow-through-dependency-views (typed error at CREATE VIEW — spec-correct, SQLView forbids params), unicode/emoji bodies byte-correct + unicode labels rejected per ASCII sql-name, interleaved runners on one shared conn, 3-level nested failure surfaces innermost label+canonical, native/fallback parity. sqlquery+viewdef 1354 passed; master gate on final tree (see launch state). |

## Personality Effectiveness addendum (SOF-SQ-03, EXPLORER final)
Winning move: name-collision and flow-through probes at the integration seam — feeding the dependency machinery inputs that alias OTHER namespaces (label 'resources' vs the source table; parameter name equal to a dependency label) is where a lesser implementation silently shadows or corrupts state; here both were safe. Second: after two hardening launches, zero defects at depth-5/diamond/nested-failure topologies indicates the recursion + in_progress cycle-set design scales; the only surviving observation was documented statelessness (diamond per-edge materialization), i.e. docstring-accurate behavior. EXPLORER is the right closer personality: it attacks topology and namespace boundaries the fix-verification launches never construct.

## Evolution Statistics row (bug_fix MT-001..MT-007, 2026-08-24)
| medterm4ds 0.0.2 integration remediation (bug_fix) | REMEDIATION ENGINEER | 7/7 fixed (5H/2M scoped + M testing) | All seeded issues RESOLVED per USER_DIRECTIVES settled decisions: dep bounded >=0.0.2,<0.0.3; HTTP $search system/searchMode/count=25 (legacy category/mode were silently dropped by FastAPI — HTTP search had ALWAYS been all-systems lexical); $expand count=1000/activeOnly=false; in-process expand primary = expand_url_pattern(include_retired=True); intensional wired in-process (count POSITIONAL); connect() RuntimeError hint + cache_indexes=True. Master gate 2832/2832; medterm in-process 4/4; live skipped (no sidecar); terminology/plumbing/loader units 99+52+216 passed. MT-008 NEW (pre-existing campaign-tree audit_mode arg_min/arg_max failure, terminology-free repro). |

## Personality Effectiveness addendum (bug_fix MT, REMEDIATION ENGINEER)
Winning move: trust the directive's verified API signatures verbatim instead of re-deriving from installed source — the one signature trap (expand_intensional_value_set's POSITIONAL count) was called out in the directive and honoring it exactly made the wiring test-first-clean. Second: when a full unit run shows failures in modules untouched by the diff, isolate them in a stripped-env subprocess (no terminology imports) to prove pre-existence before logging as NEW rather than absorbing into scope — protects single-writer discipline on the campaign tree. Third: params a remote server silently drops (FastAPI unknown-query-param) are invisible end-to-end; only transport-mock captures at the adapter boundary prove them.

## Evolution Statistics row (code_review MT remediation, 2026-08-24)
| medterm4ds 0.0.2 remediation review | CODE REVIEWER | 7/7 verified, 1 LOW latent | All MT-001..MT-007 independently re-verified (code read + live 0.0.2 spot-checks: category→system URLs all resolve in medterm's FHIR_URI_TO_SYSTEM; connect() RuntimeError hint reproduced; expand_url_pattern kwargs + expand_intensional_value_set positional-count/tuple-return confirmed against installed wheel). REV-001 LOW latent: category_to_system_param comma-joins but $search system is a single URI — dead path today (all categories single-mnemonic). Gate 2832/2832; terminology units 99; medterm in-process integration 4/4. CLEAN_WITH_NOTES. |

## Personality Effectiveness addendum (code_review MT, CODE REVIEWER)
Winning move: verify param wiring against the INSTALLED wheel's route signatures, not the sibling repo working tree (they diverge: the working tree's expand_intensional_value_set signature/annotation differs) — and read the actual `return` statement when an annotation disagrees with the directive facts (installed 0.0.2 annotates `-> list[dict]` but returns `(deduped, depth_cap_hit)`; the adapter's tuple unpack is correct). Second: a comma-join helper is a contract trap — check whether the receiving endpoint takes a scalar before approving multi-value encodings.

## Evolution Statistics row (0.0.12 campaign iter 1, 2026-08-24)
| Domain 6 Data Ingestion/resources contract | SKEPTIC | 1H/2M/2L fixed + 2 OPEN (1H architect) | 14-hypothesis adversarial probe of FHIRDataLoader: untyped patient_ref attribution fabricated phantom patients (Group-subject Condition -> patient 'g7' in retrieve CTEs), versioned refs resolve() to NULL, BOM files rejected, list-form patient refs dropped, bundle entries validated without index. All 5 fixed in fhir_loader.py + 13 tests (72/72, loader/ 216/216, gate 2832/2832). Architect: filesystem source still untyped (QA-006 HIGH) + 4-way doctrine drift (QA-007 M). |

## Personality Effectiveness addendum (Domain 6, SKEPTIC)
Winning move: read the extraction helper BEFORE probing, then grep its output column downstream — patient_ref looked like inert metadata until cte_builder.py:278 showed it becomes patient_id in every retrieve CTE, which promoted a heuristic gap to a HIGH data-corruption finding. Second: derive hypotheses from real-world data shapes (Windows BOM exports, versioned references from history-aware servers, Group-subject population-health data), not just spec corner cases — two of five finds came from interop reality, not normative text. Third: run the master gate even when you changed 'only' a loader helper; the bare-id/Group strictness change was a behavior change hiding behind an internal column.

## Evolution Statistics row (0.0.12 campaign iter 2, 2026-08-24)
| Domain 6 Data Ingestion/resources contract | HISTORIAN | 1H fixed / 2 DEFERRED | Spec-walk + regression matrix 14/14 clean; closed architect's QA-006 (filesystem untyped patient_ref aligned to shared doctrine, outputs byte-consistent with loader); QA-007 doctrine-drift and QA-008 urn:uuid-fullUrl DEFERRED with AGENTS.md doctrine table. filesystem 41/41; sources+loader 294/2; gate 2832/2832. |

## Personality Effectiveness addendum (Domain 6, HISTORIAN)
Winning move: the regression matrix on the prior launch's fixes caught nothing (good — the fixes hold), and the systematic spec walk's only find was a true scope boundary (urn:uuid fullUrl identity, net-new). Lesson: when a SKEPTIC launch just rewrote a derivation doctrine, the HISTORIAN's highest-value act is verifying the SAME contract at other implementation sites — here the filesystem source, surfacing QA-006 via the architect rather than re-proving the fixed site.

## Evolution Statistics row (0.0.12 campaign iter 3, 2026-08-24)
| Domain 6 Data Ingestion/resources contract | EXPLORER | 2M/2L fixed | Chaos battery: case-variant extensions silently skipped, unreadable file aborts directory bulk load (partial state), RecursionError untyped, circular-ref message conflated. All 4 fixed same iteration (+4 tests, 76/76; 438/2; gate 2832/2832). Domain 6 closed: 9 fixed, 3 deferred across 3 personalities. |

## Personality Effectiveness addendum (Domain 6, EXPLORER)
Winning move: attack the FILESYSTEM around the API, not just the API — the two MEDIUMs (case-variant suffixes, permission-denied abort) live in the directory-walk glue that happy-path tests never exercise with real OS state (chmod, Windows naming). Chaos on stdlib edges (RecursionError, circular refs) yielded only LOWs: the typed-error seams were mostly already tight.

## Evolution Statistics row (0.0.12 campaign iter 4, 2026-08-24)
| Domain 7 Performance/Scale | SKEPTIC | 1M fixed | Profile-first strike: executemany per-row cost 150x over Arrow bulk (in-repo load_valuesets precedent); fix landed with fallback. Scaling verified linear, no leaks, concurrency clean, resolve() decorrelated. 25k load 18.6s→0.27s. Gate 2832/2832. |

## Personality Effectiveness addendum (Domain 7, SKEPTIC)
Winning move: profile the cost split BEFORE benchmarking alternatives — attributing 99% of wall time to executemany (not python row-build) turned a vague 'loader is slow' into a citable 150x delta against an in-repo precedent, which upgrades a linear-slowdown observation into a legitimate defect under the domain's own no-linear-flag rule.

## Evolution Statistics row (0.0.12 campaign iter 5, 2026-08-24)
| Domain 7 Performance/Scale | HISTORIAN | 0 / CLEAN | 50k load 0.84s/56MB peak; evaluate_measure correct at 1k/10k/50k (males=n/2), x5 size→x1.1 time; 4x concurrent evals clean. Raw-connection CatalogException observation carried to Domain 8. |

## Evolution Statistics row (0.0.012 campaign iter 6, 2026-08-24)
| Domain 7 Performance/Scale | EXPLORER | 0 / CLEAN | Pathological battery: 416MB wide payload proportional memory; 100%-dup 50k reload 0.16s; 50k-entry bundle 0.25s; NULL-id flood; 1MB/tiny interleave byte-correct. Domain 7 closed: 1 fixed, 0 open. |

## Evolution Statistics row (0.0.12 campaign iter 7, 2026-08-24)
| Domain 8 Error Handling/API Contract | SKEPTIC | 1M fixed | Grep-first exception audit + 8 taxonomy probes. QA-014: raw CatalogException on bare connections (library-dependent!). Fixed with pre-flight duckdb_functions() guard + actionable hint. Everything else typed/actionable; ViewDefinition name-optional spec-verified. Gate 2832/2832. |

## Personality Effectiveness addendum (Domain 8, SKEPTIC)
Winning move: probe the SAME API with two libraries of different feature depth — the constant-expression library masked the registration gap that the date-dependent library exposed; library-dependent failure modes are invisible to single-example smoke tests. Second: grep the exception surface first — zero bare raises outside generated code focused the probe budget on real seams.

## Evolution Statistics row (0.0.12 campaign iter 8, 2026-08-24)
| Domain 8 Error Handling/API Contract | HISTORIAN | 0 / CLEAN | 13-probe error matrix: all typed/actionable. Two suspicions retracted by doc verification (translate_cql is a text API; fhirpath_is_valid is a SQL UDF). evaluate(None)→[] registry entry. |

## Evolution Statistics row (0.0.12 campaign iter 9, 2026-08-24)
| Domain 8 Error Handling/API Contract | EXPLORER | 2M fixed / 1 INTENDED | Boundary chaos: unknown output defs leaked CatalogException; typo'd params silently used CQL defaults (wrong results). Both fixed with listed-availables errors. QA-014 reverted→INTENDED per controlling doctrine test (Recovery Gate exercised). |

## Personality Effectiveness addendum (Domain 8, EXPLORER)
Winning move: probe with VALUES ONE TYPO AWAY from correct — mistyped parameter names and slightly-wrong definition names are the highest-frequency user errors and the lowest-frequency test subjects; both were silent failure modes. Lesson (Recovery Gate): before adding a pre-flight guard to a public API, grep the test suite for doctrine tests asserting the current failure shape — one test name (…is_not_rewritten) settles what a hundred lines of spec reading cannot.

## Evolution Statistics row (0.0.12 campaign iter 10, 2026-08-24)
| Domain 9 Audit Evidence/DQM | SKEPTIC | 1H fixed (MT-008 + hidden execution defect) | Root-caused the directives' known failing test: quantity Min/Max lost BOTH audit attribution (value cited as target) and element typing (comparisons NULL→False). Two surgical fixes; first fully-green CQL suite run (1865/0). Gate 2832/2832. |

## Personality Effectiveness addendum (Domain 9, SKEPTIC)
Winning move: assert the OBSERVED BEHAVIOR (evidence target string, evaluated boolean), not the SQL text — the unit tests asserted 'arg_min in sql' and passed vacuously against a broken execution path; a 12-line end-to-end harness with two Observations exposed both the attribution gap and the NULL-comparison defect the text assertion could never see.

## Evolution Statistics row (0.0.12 campaign iter 11, 2026-08-24)
| Domain 9 Audit Evidence/DQM | HISTORIAN | 1M fixed | Evidence walk: Sum/Avg typing verified (iter-10 fix generalizes), exclusion causality clean; found audit full-mode cartesian fan-out violating one-row-per-patient with per-row partial evidence. Fixed with per-patient aggregation — evidence now unions. cql 1867/0; gate 2832/2832. |

## Evolution Statistics row (0.0.12 campaign iter 12, 2026-08-24)
| Domain 9 Audit Evidence/DQM | EXPLORER | 0 / CLEAN | 50-obs deep-chain audit stress (1 row, 0.3s, 300-item unioned evidence), empty table, unicode evidence — all hold. Domain 9 closed: MT-008 HIGH + fan-out MEDIUM fixed. |

## Evolution Statistics row (0.0.12 campaign iter 13, 2026-08-24)
| Domain 10 Installation/Environment | SKEPTIC | 0 / CLEAN | Extensions load; fallback warning surfaces (SOF-VD-11 verified); version consistent; register idempotent; pip-check noise attributable to unrelated env packages. |

## Evolution Statistics row (0.0.12 campaign iter 14, 2026-08-24)
| Domain 10 Installation/Environment | HISTORIAN | 0 / CLEAN | Cold import 1.6s; 8/8 public modules import; version consistency across subpackages; attach/detach lifecycle idempotent and clean. |

## Evolution Statistics row (0.0.12 campaign iter 15, 2026-08-24)
| Domain 10 Installation/Environment | EXPLORER | 0 / CLEAN | Interleaved subsystems on one conn; reconnect cycles; cross-connection persistence; 6-way parallel registration race-free. Domains 6-10 closed: 11 fixed / 3 deferred. |

## Evolution Statistics row (0.0.12 campaign iter 16, 2026-08-24)
| Domain 11 API Surface Contract | SKEPTIC | 0 / CLEAN | Full entry-point battery as external consumer: all documented contracts hold; malformed inputs typed-rejected; no README-vs-behavior drift. Directives shorthands mapped (connect→create_connection; population_sql→translate_library_to_sql). |

## Evolution Statistics row (0.0.12 campaign iter 17, 2026-08-24)
| Domain 11 API Surface Contract | HISTORIAN | 1L fixed | Idempotency + determinism + signature/docstring contracts verified; found missing parameters type guard (raw AttributeError). Fixed + tested. Gate 2832/2832. |

## Evolution Statistics row (0.0.12 campaign iter 18, 2026-08-24)
| Domain 11 API Surface Contract | EXPLORER | 0 / CLEAN | Input-type chaos (bytes/Path/JSON-str/mutation/kwargs) — all typed; no parse caching. Domain 11 closed. |

## Evolution Statistics row (0.0.12 campaign iter 19, 2026-08-24)
| Domain 12 medterm4ds Integration | SKEPTIC | 0 / CLEAN | Bound in both extras verified; in_process mode constructs; search 25 graded results; intensional expand 162 codes; whole-system fhir_vs typed-unsupported with warning (policy split); suites 230+4 skip-note. |

## Evolution Statistics row (0.0.12 campaign iter 20, 2026-08-24)
| Domain 12 medterm4ds Integration | HISTORIAN | 0 / CLEAN | Retired-code split (internal membership=True, discovery active-only) verified in source+behavior; match grades/modes/batch/mapping all conform to settled MT doctrines. |

## Evolution Statistics row (0.0.12 campaign iter 21 + CLOSE, 2026-08-24)
| Domain 12 medterm4ds Integration | EXPLORER | 0 / CLEAN — CAMPAIGN COMPLETE | Chaos inputs bounded; auto_coder/notes strict-by-default verified (min_match_grade='certain'). All 21 iterations done; 13 fixed (2H/8M/3L), 3 deferred, 2 intended; gate 2832/2832. CLEAN exit. |

## Campaign summary row (0.0.12 evolution, 2026-08-24)
| 0.0.12 Evolution Campaign | 7 domains × 3 personalities | 13 fixed / 3 deferred | Domains: 6 ingestion (5+4 fixed: patient_ref doctrine, resolve versions, BOM, entry validation, perf 70-150x), 7 perf (1 fixed, rest clean), 8 errors (2 fixed + 1 doctrine), 9 audit (MT-008 root fix + fan-out, e2e evidence), 10 install (clean), 11 API (1 guard), 12 medterm (clean). Master gate 2832/2832 maintained at every fix. |

## Pipeline completion row (0.0.12, 2026-08-24)
| 0.0.12 full pipeline | ALL | evolution 21/21 CLEAN -> code_review CLEAN_WITH_NOTES -> pre_release GO -> docs_audit READY -> scribe 3-commit draft | 13 evolution defects fixed, gate 2832/2832 held at every step, wheel + website + notebooks on 0.0.12. Tree ready for Joel's review and commits. |

## Evolution Statistics row (0.0.13 campaign iter 1, 2026-08-26)
| Domain 6 Data Ingestion | SKEPTIC | 5 found / 5 fixed | Loader doctrine re-attack: fs-vs-loader divergences (versioned-absolute refs, list-form scan) + 3 error-contract gaps (ValueSet null members raw AttributeError, serialize TypeError leak, load_from_url raw JSONDecodeError). Gate 2832/2832.

## Personality Effectiveness addendum (0.0.13 iter 1, Domain 6 SKEPTIC)
Source-first hypothesis table again productive: reading the fs SQL regex list against the loader segment logic directly yielded QA-001 (versioned-absolute) without runtime probing; DuckDB json_extract_string array-path NULL semantics (it does NOT extract the first element — it returns NULL) is the reusable discovery behind QA-005. Error-contract sweeps across sibling entry points (file vs url, resource vs bundle vs ndjson) remain a reliable 3-for-1 pattern.

## Evolution Statistics row (0.0.13 campaign iter 2, 2026-08-26)
| Domain 6 Data Ingestion | HISTORIAN | 4 found / 2 fixed, 1 deferred, 1 intended | Spec-walk beyond 0.0.12 coverage: FileSystemSource directory-path doc example was broken (DuckDB read_* needs globs — fixed with dir/** expansion), duplicate JSON members now rejected per json.html "Property names SHALL be unique", urn:uuid fullUrl orphan family deferred (extends 0.0.12 QA-008), fs Bundle-as-row registered intended. Gate 2832/2832.

## Personality Effectiveness addendum (0.0.13 iter 2, Domain 6 HISTORIAN)
Walking the *documentation contract* (docstring examples) as if it were spec surfaced QA-006 — the '/data/fhir/ndjson/' directory example had never been executed. Web-verifying normative text before logging paid off again: json.html's duplicate-member SHALL is explicit only because FHIR adds it beyond RFC 8259. Deferred-family discipline (QA-008) prevents mid-campaign scope creep into net-new features.

## Evolution Statistics row (0.0.13 campaign iter 3, 2026-08-26)
| Domain 6 Data Ingestion | EXPLORER | 4 found / 4 fixed | Chained-function attack: iter-2 dir-glob fix never reached get_changed_patients (plus pre-existing raw-ndjson delta BinderException — derivation now shared); deep-nesting parse-side RecursionError wrapped; valuesets duck-type TypeError; lone-surrogate regex gate at serialize boundary (pair-aware, no false positives). Gate 2832/2832.

## Personality Effectiveness addendum (0.0.13 iter 3, Domain 6 EXPLORER)
Re-probing PREVIOUS iterations' fixes as chained interactions (register() then get_changed_patients()) found a real gap same-day — the highest-yield EXPLORER pattern this run. Regex-boundary validation needs a false-positive suite at birth (emoji pairs, literal backslash text) — cheap and prevented a class of false rejects.

## Evolution Statistics row (0.0.13 campaign iter 4, 2026-08-26)
| Domain 7 Performance | SKEPTIC | 0 / CLEAN | This campaign's own changes benchmark-first: new patient-ref SQL 5.2x FASTER than old at 10k; surrogate guard 2us/resource; Arrow bulk 0.16s@25k (0.0.12: 0.27s) ratio 62x; 50k pathological dedup 0.99s correct; no leak; 4-way concurrency clean.

## Personality Effectiveness addendum (0.0.13 iter 4, Domain 7 SKEPTIC)
Auditing your OWN same-campaign diffs first (new SQL, new guards) is the highest-duty SKEPTIC pattern — it caught nothing this time, which is itself the verification the campaign needed. Probe arithmetic bugs (expected-count math) can masquerade as data corruption — re-derive expectations before logging perf/correctness failures.

## Evolution Statistics row (0.0.13 campaign iter 5, 2026-08-26)
| Domain 7 Performance | HISTORIAN | 0 / CLEAN | Documented-contract walk at the full 50k ceiling: dict-path 8.7us/row flat, ndjson file-path 17.3us/row flat, derived-view sub-linear, resolve() 10k refs 12ms (matches doctrine), shared-db rw concurrency isolated and correct.

## Personality Effectiveness addendum (0.0.13 iter 5, Domain 7 HISTORIAN)
Verifying DOCUMENTED numbers (baselines, bands, prior findings) turns a vague perf pass into falsifiable checks — every row in the iteration table maps to a number somebody previously published. Engine constraints (DuckDB rw/ro mix) must be re-probed before attributing to the library.

## Evolution Statistics row (0.0.13 campaign iter 6, 2026-08-26)
| Domain 7 Performance | EXPLORER | 0 / CLEAN — DOMAIN 7 COMPLETE | Chaos ladder clean: 20MB resource 400ms bounded 2x mem; per-row antipattern linear 12x-over-batch (documented pattern); 500-file dir 4.4ms/file; valuesets flat 2.2us/code to 500k; concurrency clean. Domain 7 total: 0 issues / 3 personalities.

## Personality Effectiveness addendum (0.0.13 iter 6, Domain 7 EXPLORER)
Heavy-tail scaling (500k valueset codes, 20MB single resources) is cheap to probe and completes the distribution picture that ladders miss — flat per-unit cost at both extremes plus the middle ladder is strong evidence of no cliff.

## Evolution Statistics row (0.0.13 campaign iter 7, 2026-08-26)
| Domain 8 Error Handling | SKEPTIC | 5 found / 4 fixed + 1 carried | evaluate() KeyError + ctor wrap fixed; MAJOR: release commit 81957b59 shipped binaries built from uncommitted evaluator.cpp — FP-18 exact div/mod, 2^63 literals, named-group regex, inline flags, PCRE-$ all restored natively from doctrine+tests (binary rebuilt/redeployed, md5 2b3e4b79); 15 remaining lost-work parity failures carried as QA-018. Gate 2832/2832; suites 2145/0.

## Personality Effectiveness addendum (0.0.13 iter 7, Domain 8 SKEPTIC)
Binary-vs-source A/B testing (restore old binary, rerun, compare) is the decisive tool for attributing failures to YOUR changes vs pre-existing rot — one 35-second run settled what hours of code reading could not. When a doctrine names functions that grep can't find (tryDecimalModExactText), suspect lost commits before assuming doc drift; git fsck + dangling-commit scans are cheap falsification. Parity tests written-but-failing are the recovery spec when source is unrecoverable.

## Evolution Statistics row (0.0.13 campaign iter 8, 2026-08-26)
| Domain 8 Error Handling | HISTORIAN | QA-018 7/15 fixed | Lost-work restoration: temporal §6.7 validity contract (acceptance-list supersession, both engines), native fhirpath_bool 0/1 parity, 2^63 literal triple-contract (bare invalid / wrapped INT64_MIN / double-neg Decimal). Gate 2832/2832; 8 CQL translator failures carried.

## Personality Effectiveness addendum (0.0.13 iter 8, Domain 8 HISTORIAN)
When two committed tests contradict, adjudicate from three independent signals before changing code: doctrine chronology, the engine that already agrees, and GLOBAL_RULES hints. Encode the verdict in BOTH the code and the superseded test with cross-citing comments — the contradiction becomes documentation.

## Evolution Statistics row (0.0.13 campaign iter 9, 2026-08-26)
| Domain 8 Error Handling | EXPLORER | QA-018 +2/8 | CQL-04 alias-3VL value semantics + CQL-12 scalar string indexer restored across typing/classifier/lookup layers. Gate 2832/2832 (DQM REV-009 retry).

## Personality Effectiveness addendum (0.0.13 iter 9, Domain 8 EXPLORER)
Lost-work restoration is layered archaeology: the same semantic break spans typing, classification, and lowering — fix all three or the test fails at the next layer. Stopping at a design boundary (and recording it) beats forcing a change that risks the CQL-18 stored-list contracts.

## Evolution Statistics row (0.0.13 campaign iter 10, 2026-08-26)
| Domain 9 Audit/DQM | SKEPTIC | 0 new / pins hold | 172/172 DQM unit (MT-008 attribution, Quantity CTE typing, one-row-per-patient, numpy masks); persona routing verified for all exclusion/exception codes at source level.

## Evolution Statistics row (0.0.13 campaign iter 11, 2026-08-26)
| Domain 9 Audit/DQM | HISTORIAN | 0 / CLEAN — dual-numpy verified | numpy 2.4.6+py3.11 leg green (73/73 audit/evaluator/iter7-regression) completing the 1.26.4/3.10 leg from iter 10. Domain 9 COMPLETE pending EXPLORER.

## Evolution Statistics row (0.0.13 campaign iter 12, 2026-08-26)
| Domain 9 Audit/DQM | EXPLORER | 1 LOW fixed — DOMAIN 9 COMPLETE | Evidence compaction unhashable-threshold crash fixed (repr-key fallback, JSON boundary); 12-shape chaos otherwise graceful. DQM 173/173; gate 2832/2832.

## Personality Effectiveness addendum (0.0.13 iter 12, Domain 9 EXPLORER)
JSON-sourced boundaries are where Python type assumptions (hashability, list-ness) break — chaos them with objects-as-values, not just wrong scalars.

## Evolution Statistics row (0.0.13 campaign iter 13, 2026-08-26)
| Domain 10 Install/Env | SKEPTIC | 0 / CLEAN | Version constants 2/2; unsigned-dev-build WARNING verified via duckdb_fhirpath_py logger (no silent fallback); register idempotent; import 1.01s; pip-check noise = pre-existing global tooling (opencv/numpy2, litellm/openai), not fhir4ds.

## Evolution Statistics row (0.0.13 campaign iter 14, 2026-08-26)
| Domain 10 Install/Env | HISTORIAN | 1 MEDIUM fixed — DOMAIN 10 COMPLETE | CI invocation verified locally on BOTH legs (3316/3316 on 3.10 + 3.11/numpy2.4.6); 5 CI-blocking ruff violations fixed (1 campaign + 4 release-commit drift). Lint clean.

## Personality Effectiveness addendum (0.0.13 iter 14, Domain 10 HISTORIAN)
Run the CI workflow's EXACT commands locally when CI is dark — the lint step caught drift the pytest-only gates never see. ruff --fix is safe for these classes (parens/imports/escapes) but re-run affected suites anyway.

## Evolution Statistics row (0.0.13 campaign iter 15, 2026-08-26)
| Domain 10 Install/Env | EXPLORER | 1 MEDIUM fixed — DOMAIN 10 COMPLETE | Site-packages orphan carried the stale 0.0.12 native binary (default import path!); synced to 39bea478, md5 parity across all surfaces. Chaos: shadowing conservative, txn-abort native, mid-cursor OK.

## Personality Effectiveness addendum (0.0.13 iter 15, Domain 10 EXPLORER)
Test suites prove the REPO; users import from site-packages — deployment-parity checks (GLOBAL_RULES md5 doctrine) are the only guard for that gap, and they belong in every EXPLORER install-domain pass.

## Evolution Statistics row (0.0.13 campaign iter 16, 2026-08-26)
| Domain 11 API Surface | SKEPTIC | 0 / CLEAN | All documented entry points verified; README examples run verbatim (VD example + standalone FHIRPath); sqlquery/terminology/notes/dqm symbols present; signatures match docs.

## Evolution Statistics row (0.0.13 campaign iter 17, 2026-08-26)
| Domain 11 API Surface | HISTORIAN | 1 LOW fixed | README evaluate_measure .df() drift corrected; full contract walk (types/errors/idempotency) otherwise green across all entry points.

## Evolution Statistics row (0.0.13 campaign iter 18, 2026-08-26)
| Domain 11 API Surface | EXPLORER | 0 / CLEAN — DOMAIN 11 COMPLETE | VD-over-attach, detach round trip, parsed-object->generate, bare-con execution (native catalog error, registry) all verified.

## Evolution Statistics row (0.0.13 campaign iter 19, 2026-08-26)
| Domain 12 medterm4ds | SKEPTIC | upgrade executed | 0.0.3 installed + diff-audited (additive + HF_REVISION default change flagged); extras bounded >=0.0.3,<0.0.4; 4/4 in-process + 77 unit re-verified; gate 2832/2832.

## Evolution Statistics row (0.0.13 campaign iter 20, 2026-08-26)
| Domain 12 medterm4ds | HISTORIAN | 0 / CLEAN | Retired-split, extract kwargs, search semantics, match grades all re-derived from 0.0.3 source — unchanged from 0.0.2 doctrine; additive-only deltas.

## Evolution Statistics row (0.0.13 campaign evolution COMPLETE, 2026-08-26)
| 0.0.13 Evolution | 7 domains x 3 personalities + 1 continuation | 23 found / 22 fixed / 1 carried HIGH | Domains: 6 ingestion (13 found, 12 fixed, 1 deferred), 7 perf (clean x3), 8 errors (5 + lost-work restoration epic), 9 DQM (1 fixed, dual-numpy verified), 10 install (lint + deployment parity), 11 API (1 doc drift), 12 medterm (0.0.3 upgrade executed). Gate 2832/2832 throughout. Exit DEGRADED: QA-018 carries 5 lost-work parity failures for Joel (recover uncommitted tree; full-tree CI).

## Personality Effectiveness addendum (campaign close, 2026-08-26)
The campaign's dominant discovery was not domain-specific: the 0.0.12 release lost uncommitted native/translator work. Binary-vs-source A/B, doctrine archaeology, and parity-tests-as-recovery-spec restored 10/15. Process fixes that would have prevented it: commit-before-build discipline, full-tree CI on release commits, ruff in every gate.

## Pipeline completion row (0.0.13, 2026-08-26)
| 0.0.13 full pipeline | ALL | evolution 21+1 iters (DEGRADED exit: QA-018 carried) -> code_review CLEAN_WITH_NOTES -> pre_release GO -> docs_audit READY (e2e 17/17) -> scribe 3-commit draft | 22 fixes; gate 2832/2832 at every step; wheel + website + notebooks on 0.0.13; stale bulk-publisher 0.0.10 wheel caught; tree ready for Joel's review and commits.
