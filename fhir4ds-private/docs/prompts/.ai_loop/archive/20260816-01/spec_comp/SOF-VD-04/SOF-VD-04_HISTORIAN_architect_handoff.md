# Architect Handoff — SOF-VD-04 HISTORIAN iter 1 fresh run (2026-07-03)

## Phase: ARCHITECT (Structural Audit)

## Golden Standard for SOF-VD-04
The SOF-VD-04 surface (`column.collection`, `column.type`, `column.tag`) must
satisfy these falsifiable architectural invariants:

1. **Single source of truth for field validation**: Every spec-owning
   dataclass (`Column`, `ColumnTag`) must enforce its invariants in
   `__post_init__` using the same canonical helpers used by parser,
   `from_dict`, `to_dict`, and downstream SQL generation.
2. **No silent fallbacks for malformed input**: Whitespace-only strings,
   non-dict tag items, non-string types, and missing required fields must be
   rejected at the model boundary with typed errors — never silently coerced.
3. **Spec-grounded cardinality enforcement**: A non-collection column that
   produces multiple values at runtime must raise a typed error matching the
   spec's "Multiple values found but not expected for column" rule.
4. **Type is a hint, not a coercion**: `column.type` accepts FHIR
   StructureDefinition URIs, primitive type names, fragment forms, and
   unknown external URIs (preserved verbatim). Type-mismatch at runtime is
   reported, not silently coerced.
5. **Tag is 0..* with required name/value**: Empty array accepted. Each item
   must have non-empty name and value. Duplicate names allowed (no dedup
   rule). Parser rejects the plural `tags` form.
6. **Default `collection=false` is canonical**: Both direct construction and
   parser paths default to `False` (not `None`, not missing). `to_dict()`
   omits the default to match the spec's serialized form.

## Code Audit
Audit dimensions checked against `fhir4ds/viewdef/types.py`,
`fhir4ds/viewdef/parser.py`, `fhir4ds/viewdef/generator.py`:

- **Generalizability**: No hardcoded resource types, measure IDs, or
  constants in the collection/type/tag validation paths. ✅
- **Abstraction Integrity**: `Column.__post_init__` (types.py:557-588)
  invokes the canonical `validate_column_fields`,
  `validate_optional_boolean`, and `ColumnType.from_string` helpers — the
  same helpers used by parser (`_parse_column`, parser.py:113-173),
  `to_dict()` (types.py:590-620), and `SQLGenerator._validate_column_shape`
  (generator.py:709-722). No layer reaches past its neighbor. ✅
- **Silent Fallbacks**: `validate_required_string` (types.py:47-62) rejects
  whitespace-only strings. `validate_optional_uri_string` (types.py:88-96)
  rejects empty/whitespace URIs. `validate_optional_boolean`
  (types.py:74-78) rejects non-bool values. No silent coercion detected. ✅
- **Test-Driven Hacks**: No special-cased logic for specific test fixtures.
  The multi-value cardinality guard is data-driven
  (`array_length(fhirpath(...)) > 1`), not a hardcoded path match. ✅
- **Coupling**: `ColumnTag` is self-contained (validates its own name/value
  in `__post_init__`). `Column` consumes `ColumnTag` via composition, not
  inheritance. Loose coupling maintained. ✅
- **Performance Critical Paths**: No repeated JSON parsing or redundant
  DuckDB round-trips in the column validation hot path. ✅

## Empirical Validation & QA Audit
- ViewDefinition pytest: **1055/1055** PASS
- Full conformance: **2822/2822** (ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47) — preserved per `PROC_VALIDATION.md` baseline.

**QA Enforcer Gate**: HISTORIAN's probe was NOT lazy. It systematically
walked all 6 spec items with 43 assertions covering direct construction,
parser, `to_dict()`, SQL generation, AND DuckDB runtime execution. The
runtime assertions (2b multi-value error, 3d collection=true semantics, 5c
type-mismatch reporting) demonstrate the QA agent tested execution
behavior, not just parse-time validation. **No QA retry required.**

## Issue Logging & State Hygiene
Zero new issues logged. No `RESOLVED`/`VERIFIED` issues to archive this
iteration (the `issues` array was empty on entry).

## Handoff Compression
- **QA**: 43-assertion systematic spec-walkthrough; all 6 SOF-VD-04 items
  verified CLEAN across direct construction, parser, `to_dict()`, SQL
  generation, and DuckDB runtime. Notable confirmations: multi-value
  non-collection raises `Invalid Input Error` matching spec §2.2.1;
  collection=true returns whole collection matching spec §2.2.1 step 3;
  type-mismatch reporting matches spec §Column Types; tag 0..* with required
  name/value enforced uniformly.
- **Engineer**: No remediation required. Zero issues to triage. No source
  changes. Baseline preserved.

## Recommended Fix Order
Empty. No outstanding issues.

## Conclusion
**Structural health: SOUND.** The SOF-VD-04 surface satisfies all 6 golden
standard invariants. The post-SOF-VD-03 SKEPTIC 2026-07-03 hardening
(`Column.__post_init__` enforcing all spec invariants at construction time)
and the SOF-VD-03 EXPLORER 2026-07-03 whitespace rejection fix remain intact.
No architectural drift detected. Clean exit eligible at `min_iterations=1`.
