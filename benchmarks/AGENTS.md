# FHIR4DS Benchmarks

This directory contains performance benchmarking tools and results for the `fhir4ds` engine.

## Overview

Benchmarks are focused on comparing `fhir4ds` performance and accuracy against reference implementations (e.g., HAPI FHIR / Clinical Reasoning Java engine).

## Structure

```
benchmarks/
├── clinical-reasoning/    # Java Clinical Reasoning reference engine
├── output/                # Generated results (SQL, CSV, Stats)
├── comparison.py          # Cross-engine result comparison logic
├── run_comparison.py      # Execution script for cross-engine benchmarks
├── COMPARISON.md          # Latest benchmark results
└── UPSTREAM_ISSUES.md     # Tracked test-data issues in official suites
```

## Running Benchmarks

### Cross-Engine Comparison
To compare `fhir4ds` (Python/C++) against the Java reference implementation:

```bash
cd benchmarks
python3 run_comparison.py --runs 5
```

## Related Data
Test data and official eCQM content used by these benchmarks are located in the top-level `tests/data/` directory.

## Accuracy Verification
Functional verification and conformance testing have been moved to the core library. See [fhir4ds/dqm/tests/conformance/README.md](../../fhir4ds/dqm/tests/conformance/README.md) for details on the conformance runner.

## License
Apache 2.0
