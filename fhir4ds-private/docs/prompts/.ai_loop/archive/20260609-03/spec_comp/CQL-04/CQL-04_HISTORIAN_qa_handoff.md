# QA Handoff - CQL-04 / HISTORIAN

## Scope

Spec compliance chunk `CQL-04`: CQL logical operators `And`, `Or`, `Xor`, `Implies`, and `Not`.

HISTORIAN pass traced the official CQL 1.5.3 logical operator truth tables and then exercised:

- Direct public DuckDB helper/macros on native-loaded and forced Python fallback connections.
- Legacy `logicalImplies` Boolean-text handling on native, fallback, and no-Python C++ extension surfaces.
- Translated scalar CQL precedence: `and`, left-to-right `or`/`xor`, low-precedence `implies`, and `between ... and ...` bound-separator handling.
- Translated Patient-context query `let`/`where`/`return` population SQL on native and forced fallback registrations.
- Static invalid operands including literals, clinical/complex values, lists, tuples, intervals, typed aliases, and `as Any` chains.

## Findings

### QA-001 - HIGH - RESOLVED

Non-Boolean values wrapped in `as Any` / `as System.Any` bypassed logical operand validation and emitted raw SQL truthiness, e.g. `(1 as Any) and true` became `1 AND TRUE`, and clinical/Quantity/List/Tuple/Interval shapes could reach `AND`/`OR`.

Spec basis: CQL Appendix B logical operator signatures require Boolean operands for `And`, `Or`, `Xor`, `Implies`, and `Not`. `as Any` is a type assertion, not a conversion to Boolean.

### QA-002 - HIGH - RESOLVED

`singleton from ([Observation] ... let ... where ... return ...)` inside Patient context built uncorrelated count/value subqueries. With two patients and one Observation each, the singleton cardinality check counted both patients' rows and returned `NULL` for both instead of the per-patient logical result.

Spec basis: Patient-context retrieves are subject-scoped. Logical expressions inside query `let`/`where`/`return` must be evaluated for the current subject's source rows.

## Validation

- `python3 .temp/qa/cql04_historian_probe.py` passed.
- `pytest -q fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py` passed `22 passed`.
- Broader CQL subset passed `113 passed`:
  - `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py`
  - `fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py`
  - `fhir4ds/cql/tests/unit/test_parser.py`
- Full conformance passed:
  - ViewDefinition `134/134`
  - FHIRPath `935/935`
  - CQL `1706/1706`
  - DQM `47/47`
  - Overall `2822/2822`
