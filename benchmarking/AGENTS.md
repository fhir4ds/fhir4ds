# FHIR Measure Benchmarking

This benchmarking infrastructure evaluates CQL measures using the unified `fhir4ds` engine
(DuckDB SQL translation) and compares patient population membership against expected MeasureReport results.

## C++ Extension Support

The runner loads compiled C++ DuckDB extensions by default for native-speed FHIRPath and CQL
evaluation. The `USE_CPP_EXTENSIONS` environment variable controls the UDF backend:

| Setting | Behavior |
|---------|----------|
| `USE_CPP_EXTENSIONS=1` (default) | Load C++ `.duckdb_extension` binaries |
| `USE_CPP_EXTENSIONS=0` | Use Python UDFs from `fhir4ds.cql.duckdb` |

The C++ extensions (`extensions/fhirpath`, `extensions/cql`) must be built before use:

```bash
cd extensions/fhirpath && cmake --build build/release --config Release -j 8
cd extensions/cql      && cmake --build build/release --config Release -j 8
```

The runner copies extensions to `/tmp/duckdb_cpp_ext/` on first use to avoid WSL2 NTFS
filesystem instability with memory-mapped files.

## Setup

```bash
# Install the unified package from the root
pip install -e ..
git submodule update --init --recursive  # fetch data/ecqm-content-qicore-2025
```

## CLI Usage

```bash
# Run all 2025 measures (default)
python -m benchmarking.runner

# Run all 2026 measures
python -m benchmarking.runner --suite 2026 --skip-errors

# Run a specific measure (2025)
python -m benchmarking.runner --measure CMS165
```

## Architecture

```
benchmarking/
├── runner/                       # Python benchmarking runner
│   ├── cli.py                    # CLI (--suite 2025/2026, auto-discovery)
│   ├── config.py                 # Paths and MeasureConfig dataclass
│   ├── database.py               # DuckDB setup (C++ ext loading)
│   ├── test_loader.py            # Test data loading
│   ├── measure_runner.py         # fhir4ds execution
│   ├── result_writer.py          # CSV/JSON output
│   └── comparison.py             # Result comparison logic
├── data/ecqm-content-qicore-2025/ # 2025 test data and CQL measures (submodule)
├── data/dqm-content-qicore-2026/  # 2026 draft content (git clone)
├── UPSTREAM_ISSUES.md            # Tracked upstream test-data issues
├── clinical-reasoning/           # Java clinical-reasoning benchmark
└── output/                       # Generated results
```

## Accuracy Baseline (C++ extensions, 2025 suite, 46 measures)

Results verified 2026-03-27 — C++ extensions at **full parity** with Python across all 46
runnable measures.

## Related Documentation

- [../AGENTS.md](../AGENTS.md) - Overall repository documentation
- [UPSTREAM_ISSUES.md](UPSTREAM_ISSUES.md) - Tracked upstream issues
- [COMPARISON.md](COMPARISON.md) - Java vs Python comparison results

## License

Apache 2.0
