# QA Handoff — SOF-SQ-01 EXPLORER launch (2026-08-24)

Personality: EXPLORER (fuzzer/abuser). Chunk: SQL-on-FHIR Analytics Layer —
SQLQuery/SQLView Library profiles + sql-must-be-sql-expressions invariant.
Spec source of truth: /mnt/d/sql-on-fhir-v2 @ upstream/sqlquery-view-sources
(input/fsh/profiles/library-profiles.fsh, terminology.fsh, models.fsh sql-name).

## Probes executed (all typed SQLQuery*Error, no crashes)
- content[] at 100 entries mixed valid/invalid: first bad entry reported with
  index (content[57]); 100 valid entries parse.
- base64 edges: URL-safe alphabet, embedded whitespace/newlines, missing or
  extra padding, empty-string data, non-string data — all typed rejects
  (QA-001 intended strictness). Unicode SQL with BOM decodes and round-trips
  byte-exact; 1MB SQL parses fine.
- Profile dispatch: official + legacy canonicals, |version|-pinned, both
  families declared for the same kind (accepted), SQLQuery+SQLView both
  declared (rejected as ambiguous), 9 foreign profiles + 1 SQLQuery
  (dispatches), meta null / profile null / profile non-list (typed rejects).
- relatedArtifact: 50 entries; label colliding with parameter name (allowed);
  resource "http://vd|1.0.0#x" (accepted verbatim); bad sql-name label →
  SQLQueryValidationError; non-depends-on type rejected.
- parameter matrix: all FHIR primitives incl. integer64/positiveInt/uuid/oid
  accepted; complex type rejected; 64 params; duplicate names allowed (spec
  does not forbid); missing/incorrect use rejected; SQLView parameter 0..0
  enforced (empty list tolerated).
- contentType variants: ;dialect=duckdb, ;charset=utf-8, ;dialect=postgresql
  pass invariant; vnd.sql / text/sql / Application/SQL rejected per
  startsWith invariant (QA-003 deferred runner-side charset note).
- Unknown shapes: content as string, input int/list/bad-JSON-string,
  wrong resourceType, meta/type wrong types — typed errors everywhere.
- Round-trip: gen1==src (verbatim extra_fields, meta, type, extensions,
  unknown custom keys), gen2==gen1, gen3==gen2; stable after mutations
  (param type change + added content entry). SQLView legacy canonical
  preserved, never rewritten.
- Runner end-to-end (register_fhirpath + resources table): parameterized
  query ($gender), dict and parsed-object inputs, SQLView→SQLQuery chain,
  missing parameter, foreign dialect, str→integer coercion — all correct
  typed behavior.

## Result
Zero non-terminal CRITICAL/HIGH/MEDIUM issues. 3 LOW records: QA-001
INTENDED, QA-002 INTENDED, QA-003 DEFERRED. sqlquery suite 70/70; master
gate 2832/2832. Clean exit at min_iterations=1.
