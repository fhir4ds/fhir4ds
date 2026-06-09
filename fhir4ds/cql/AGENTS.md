# fhir4ds.cql AGENTS.md

## CQL `$cql` Facade Design Notes

- The planned FHIR `$cql` facade is CQL-specific and belongs under
  `fhir4ds/cql/fhir_server/`; do not create a broad generic FHIR server
  namespace for this V1 conformance harness.
- Keep HTTP/FHIR `Parameters` handling outside the translator. The translator
  may expose immutable result metadata, but it must not know about
  `cqframework/cql-tests-runner` or FHIR operation envelopes.
- Result serialization for the runner must be CQL-metadata-driven. Do not pick
  `valueDate`, `valueTime`, `valueCoding`, `valueRange`, tuple parts, or list
  repetition based only on DuckDB physical type or JSON/VARCHAR transport shape.
- Current runner discovery on 2026-06-04: `$cql` requests post a FHIR
  `Parameters` resource with one `expression` `valueString`; responses are
  extracted from `return` parameters, nested `part`, repeated names, null/empty
  extensions, and `evaluation error` OperationOutcome parameters.
- For V1, keep the HTTP adapter dependency-free unless a later approved design
  adds an optional ASGI/web framework extra. Runner acquisition belongs in a
  conformance script, not as a git submodule.
- Facade parser validation is a public HTTP boundary. Malformed nested
  `Parameters` value shapes must raise typed `CQLFacadeError` results, not
  Python `TypeError`, `KeyError`, `InvalidOperation`, or `JSONDecodeError`
  leaks through `handle_cql_operation()` or the stdlib HTTP adapter.
- Keep the facade request-size cap configurable through
  `CQLServerConfig.max_request_bytes` and covered by HTTP tests. The server is
  a local conformance harness, but it still accepts arbitrary runner request
  bodies.

## Release 0.0.8 Domain 3 HISTORIAN Rerun

- VERIFIED CLEAN on 2026-06-07. Fresh translated-execution probes covered CQL
  interval boundary semantics for `during`, `overlaps`, `meets`,
  `starts`, `ends`, `overlaps before`, and `overlaps after` across
  native-loaded C++ and forced Python fallback DuckDB registrations.
- Keep future interval translator changes aligned with both local interval
  pytest coverage and official `CqlIntervalOperatorsTest.xml`; the fresh
  rerun baseline was targeted pytest 438/438 and CQL conformance 1706/1706
  with interval operators 412/412.

## Release 0.0.8 Domain 4 EXPLORER Rerun

- `QA-003` VERIFIED on 2026-06-07. CQL-authored interval parameter defaults
  must preserve parsed `low`, `high`, `lowClosed`, and `highClosed` metadata
  through population SQL generation. Do not flatten
  `Interval<DateTime> default Interval[@start, @end)` into a date-only closed
  tuple.
- Runtime two-tuple parameter bindings retain their compatibility behavior as
  closed intervals. The structured-default path is specifically for defaults
  parsed from CQL, where the authored bracket syntax is known.
- Keep measurement-period changes covered by
  `fhir4ds/cql/tests/integration/test_population_measurement_period.py`,
  native-loaded and forced Python fallback DQM-style probes, CMS integration,
  and CQL/DQM conformance.

## Release 0.0.8 Domain 6 SKEPTIC Rerun

- VERIFIED CLEAN on 2026-06-07 for `FHIRDataLoader` ingestion boundaries.
  Strict NDJSON and Bundle loads must validate the full batch before deleting
  or inserting rows, including duplicate identities queued for replacement,
  valid-JSON non-object records, missing/invalid `resourceType`, invalid ids,
  and decoded non-standard JSON numbers such as `NaN`.
- Non-strict NDJSON remains skip-and-warn. Keep
  `.temp/qa/domain6_skeptic_probe.py`,
  `fhir4ds/cql/tests/unit/test_fhir_loader.py`, source adapter tests, DQM
  integration, and DQM conformance aligned when changing loader ingestion.

## Release 0.0.8 Domain 7 ARCHAEOLOGIST Finding

- `QA-004` opened and was remediated on 2026-06-07 for DQM benchmark drift,
  not for loader scale.
  The loader probe remained linear and heap-stable, but current DQM performance
  comparison flagged 7 timing regressions against `benchmarks/baselines/dqm_2025.json`.
- CMS2 is the sentinel: 47/47 accuracy remained intact, but current generated
  SQL is about 1.55 MB / 11.6 s versus the checked-in 406 KB / 2.6 s baseline.
  Current SQL contains later correctness surfaces such as `CQLListContainsEq`,
  `CalculateAgeInYearsAt`, `ToDate`, `fhirpath_number`, and `CQLMessage`
  branches that older local baseline-like artifacts did not.
- The release baseline was intentionally refreshed from the validated current
  DQM report rather than weakening thresholds. When changing CQL list equality,
  age calculation, temporal conversion, dynamic FHIR numeric handling, or
  `Message`/`ToDaily` lowering, rerun the DQM performance report and either
  recover the SQL/timing shape or intentionally refresh the DQM baseline with
  release notes explaining the correctness cost.
