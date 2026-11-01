# QA Handoff - Fresh 0.0.5 Rerun

Scope:
- Reran the 10-iteration evolution phase from scratch per user instruction.
- Did not use archived loop reports as evidence of completion.

Fresh QA coverage:
- Iteration 1: FHIRPath high-risk native parity, 2 passed.
- Iteration 2: FHIRPath broad parity initially found failures in conversion/equality/type wrappers; fixed and reran, 13 passed.
- Iteration 3: Remaining FHIRPath parity/integration, 41 passed.
- Iteration 4: CQL core parity, 18 passed.
- Iteration 5: CQL wide parity, 33 passed, 5 skipped.
- Iteration 6: ViewDefinition suite, 691 passed.
- Iteration 7: DQM suite, 70 passed, 2 warnings.
- Iteration 8: FHIRPath unit/duckdb unit suite initially caught patch regression; corrected and reran, 1075 passed, 1 warning.
- Iteration 9: CQL DuckDB plus source adapter suite, 652 passed, 5 skipped.
- Iteration 10: Full conformance initially failed FHIRPath 934/935, then passed after the C++ equality fix.

Issues found:
- QA-001 HIGH: Python/C++ FHIRPath wrapper drift around `toDecimal()`, multi-item equality, and multi-item `as()`.
- QA-002 HIGH: Native C++ FHIRPath multi-item `=`/`!=` returned empty instead of ordered collection equality results.

Final conformance:
- ViewDefinition: 134/134
- FHIRPath R4: 935/935
- CQL: 1706/1706
- DQM QI Core 2025: 47/47
- Overall: 2822/2822
