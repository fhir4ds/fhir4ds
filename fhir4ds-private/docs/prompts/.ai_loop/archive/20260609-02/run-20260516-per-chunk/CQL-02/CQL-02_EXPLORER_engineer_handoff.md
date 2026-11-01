# Engineer Handoff - CQL-02 EXPLORER

Iteration: 1
Status: all QA issues resolved

## Fixed

### CQL02-EXPLORER-001

Root cause: CQL Concept metadata was treated as a single Code dictionary in the `~` translator. Concept dictionaries carry a `codes` list and no top-level `code`/`system`, so static comparisons used missing fields and dynamic FHIR comparisons emitted unconstrained `coding.exists()`.

Fix:

- Normalized Code and Concept operands to lists of Code entries.
- Implemented static Code/Concept and Concept/Concept equivalence as non-empty code/system intersection, ignoring display/version per CQL 1.5.3.
- Generated multi-code FHIRPath predicates for resource-side `CodeableConcept ~ Concept`.

Files:

- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/fhirpath_builder.py`
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`

### CQL02-EXPLORER-002

Root cause: Static clinical type inference did not recurse through `singleton from` or query `let`/`return` aliases, so clinical JSON values fell through to FHIR `resourceType` checks.

Fix:

- Added static clinical type inference for `singleton from`.
- Added query return inference, including query `let` aliases.
- Added native/fallback population SQL execution coverage.

Files:

- `fhir4ds/cql/translator/expressions/_query.py`
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py -q` -> 11 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_cql.py` -> 1706/1706
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql fhir4ds/cql/duckdb/tests -q` -> 515 passed, 5 skipped
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` -> 2822/2822

No C++ native code changes were required.
