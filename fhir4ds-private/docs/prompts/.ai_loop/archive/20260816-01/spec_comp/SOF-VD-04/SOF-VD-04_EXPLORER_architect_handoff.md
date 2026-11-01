# Architect Handoff — SOF-VD-04 EXPLORER iter 1 fresh run (2026-07-03)

## Phase: ARCHITECT (Structural Audit)

## Golden Standard for SOF-VD-04 (under chaos / abuse)
The SOF-VD-04 surface (`column.collection`, `column.type`, `column.tag`)
must remain structurally sound when subjected to pathological inputs. The
golden standard invariants established for HISTORIAN iter 1 (single source
of truth for validation, no silent fallbacks, spec-grounded cardinality,
type is a hint not a coercion, tag 0..* with required name/value, default
`collection=false` is canonical) are the baseline; EXPLORER adds three
abuse-resistance invariants:

7. **Re-validation on serialization**: Every spec-owning dataclass must
   re-validate its fields in `to_dict()` so post-construction mutation
   cannot bypass invariants. (`Column.to_dict` re-runs
   `validate_column_fields`, `validate_optional_boolean`, and
   `validate_optional_uri_string`. `ColumnTag.to_dict` re-runs
   `validate_required_string`.)
8. **Type confusion rejection at every entry point**: Direct dataclass
   construction, `from_dict`, parser, and `to_dict` must all reject
   non-bool collection, non-string type, and non-dict tag items with
   typed errors. No path may silently coerce.
9. **No crash on unknown external URIs**: `column.type` accepting an
   opaque external URI must not crash SQL generation, even under iterator
   context. The type is a hint per spec §Column Types.

## Code Audit
Audit dimensions checked against `fhir4ds/viewdef/types.py`,
`fhir4ds/viewdef/parser.py`, `fhir4ds/viewdef/generator.py`:

- **Generalizability (abuse-resistance)**: No hardcoded resource types or
  magic constants in collection/type/tag validation paths. The type-confusion
  rejection paths use `isinstance(value, bool)`, `isinstance(value, str)`,
  `isinstance(item, dict)` — type-system-based, not string-pattern-based.
  ✅
- **Abstraction Integrity**: `Column.__post_init__` (types.py:557-588) and
  `Column.to_dict` (types.py:590-620) both invoke the canonical
  `validate_column_fields`, `validate_optional_boolean`,
  `validate_optional_uri_string`, and `ColumnType.from_string` helpers.
  Parser `_parse_column` (parser.py:113-173) uses the same helpers. No
  layer reaches past its neighbor. ✅
- **Silent Fallbacks (CRITICAL)**: EXPLORER's probe specifically targeted
  silent-fallback paths:
  - `Column.to_dict()` re-validates `collection`, `type`, and `tag` after
    mutation (verified by item1 and item6 mutation assertions). ✅
  - `ColumnTag.to_dict()` re-validates `name` and `value` after mutation
    (verified by item6 tag-name-empty-mutation assertion). ✅
  - Type-confusion rejection at all four entry points
    (direct/from_dict/parser/to_dict) verified. ✅
  - Unknown external URI SQL generation does not crash. ✅
- **Test-Driven Hacks**: No special-cased logic for specific test fixtures.
  The cardinality and type guards are data-driven
  (`array_length(...) > 1`, `declared type <T>`). ✅
- **Coupling**: `ColumnTag` is self-contained. `Column` consumes `ColumnTag`
  via composition. ✅
- **Performance Critical Paths**: No repeated JSON parsing or redundant
  DuckDB round-trips in the column validation hot path. The 1000-tag and
  10000-char stress tests pass quickly. ✅

## Empirical Validation & QA Audit
- ViewDefinition pytest: **1055/1055** PASS
- Full conformance: **2822/2822** (ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47) — preserved per `PROC_VALIDATION.md` baseline.

**QA Enforcer Gate**: EXPLORER's probe was NOT lazy. It systematically
abused all 6 spec items with 68 assertions covering type confusion at all
four entry points (direct/from_dict/parser/to_dict), pathological URI
strings (control chars, unicode, whitespace, case sensitivity), tag chaos
(type confusion, 1000-tag stress, 10000-char values, unicode, mutation),
and combined pathological inputs. The mutation re-validation assertions
(item1 collection-mutation, item6 tag-name-empty-mutation, item6
tag-None-mutation) demonstrate the QA agent tested serialization-time
re-validation, not just construction-time validation. **No QA retry
required.**

## Issue Logging & State Hygiene
Zero new issues logged. No `RESOLVED`/`VERIFIED` issues to archive this
iteration (the `issues` array was empty on entry).

## Handoff Compression
- **QA**: 68-assertion pathological/abuse probe; all 6 SOF-VD-04 items
  verified CLEAN under type confusion, URI chaos, tag stress, and
  post-construction mutation. Critical confirmations: `to_dict()`
  re-validates so mutation cannot bypass invariants; type-confusion
  rejected at all four entry points; unknown external URIs do not crash
  SQL generation; 1000-tag and 10000-char stress pass.
- **Engineer**: No remediation required. Zero issues to triage. No source
  changes. Baseline preserved.

## Recommended Fix Order
Empty. No outstanding issues.

## Conclusion
**Structural health: SOUND under abuse.** The SOF-VD-04 surface satisfies
all 9 golden standard invariants (6 from HISTORIAN + 3 abuse-resistance
additions from EXPLORER). The post-SOF-VD-03 hardening and SOF-VD-03
EXPLORER whitespace rejection fix remain intact. No architectural drift
detected. Clean exit eligible at `min_iterations=1`.
