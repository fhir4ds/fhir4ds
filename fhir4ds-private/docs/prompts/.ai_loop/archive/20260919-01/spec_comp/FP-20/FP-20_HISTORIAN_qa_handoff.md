# QA Handoff — FP-20 HISTORIAN (iteration 1, 2026-08-18)

## Scope
FHIRPath R4 §9–§12, fresh angles beyond the SKEPTIC launch. Spec grounding:
hl7.org/fhirpath/2018Sep (fetched) for trace()/as/is/ofType/type() singleton
semantics, logical-operator singleton evaluation, and the official 2018Sep
FHIRPath.g4 (downloaded to /tmp/fp2018.g4) for the grammar comparison.

## Probes (PYTHONPATH=/mnt/d/fhir4ds)
- `.temp/qa/fp20_historian2_probe.py` — 48 dual-path exprs (%context deep
  nav/identity, reflection matrix, is/as/ofType, §11 arg type-safety,
  §12 primitive equality): 0 parity diffs.
- `.temp/qa/fp20_historian3_probe.py` — core-engine §10/§11/§12 matrix
  (type() on all literal kinds, uri-family field typings, operator
  type-safety errors).
- `.temp/qa/fp20_historian4_probe.py` — focused dual-path parity on
  uri/canonical field typings: 1 parity diff (QA-001).

## Verified-clean (spec-confirmed)
- trace() returns its INPUT (spec quote); `trace('t',1)+1` error is correct.
- type() on multi-item collections returns per-element TypeInfo — matches
  spec example `('John'|'Mary').type()`.
- `true and 1` -> true via Singleton Evaluation of Collections (spec §logic).
- 1/0, 1 div 0, 1 mod 0 -> {}: unspecified in 2018Sep, consistent.
- `{1,2}` syntax error CONFORMS: official 2018Sep grammar `literal : '{' '}'`
  has no non-empty literal-list production (QA-002 INTENDED).
- `name is List<...>` rejected: official typeSpecifier : qualifiedIdentifier.
- `gender as FHIR.string` empty while `is` true: fixture-pinned exact-match
  doctrine (FP-15), correctly implemented on both engines.
- as/ofType/`is` matrix on System/FHIR primitives otherwise consistent;
  wrong-type function args error on core / empty+invalid classify on UDFs.

## Findings
- QA-001 MEDIUM OPEN (parity + spec): `meta.profile.type().name` ->
  native 'uri' vs fallback 'string'; spec type is `canonical` (canonical->uri
  in type2Parent.json). `meta.source.type().name` -> 'string' both paths;
  spec type is `uri`. Root cause: evaluator.cpp fhirFieldType hardcodes
  profile->uri and omits source; fhir_path_to_type.json lacks .profile/.source.
- QA-002 LOW INTENDED: literal-list rejection is 2018Sep-conformant.
- QA-003 LOW INTENDED: `.system`->uri shared approximation (ContactPoint.system
  is code per R4) — pre-existing, fixture-unpinned, no parity diff.

## Handoff to Remediation
Fix QA-001 root cause on both engines: add `.profile`: canonical, `.source`:
uri to fhir4ds/fhirpath/models/r4/fhir_path_to_type.json (data-driven) and
align evaluator.cpp fhirFieldType (profile -> canonical, add source -> uri),
rebuild + redeploy fhirpath.duckdb_extension, add dual-path parity test.
Then document QA-002/QA-003 in AGENTS.md.
