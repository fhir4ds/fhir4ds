# Contributing to FHIR4DS

Thank you for your interest in contributing to FHIR4DS! 

## Contributor License Agreement (CLA)

To maintain our ability to offer FHIR4DS under both open-source (AGPL v3) and commercial licenses, we require all contributors to agree to our Contributor License Agreement (CLA).

If you have questions about the CLA or wish to discuss specific contribution terms, please contact **fhir4ds@gmail.com**.

## Development Setup

The project uses a unified namespace `fhir4ds`. To set up your local environment:

```bash
# Clone and enter the repo
git clone https://github.com/fhir4ds/fhir4ds.git
cd fhir4ds

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

## Running Tests

Tests are located within each subpackage in the `fhir4ds/` directory.

```bash
# Run all tests
pytest fhir4ds/

# Run specific subpackage tests
pytest fhir4ds/cql/tests/
```

## C++ Extension Development

If you are modifying the C++ extensions, they are located in `extensions/`:

```bash
cd extensions/fhirpath
cmake -B build/release -D CMAKE_BUILD_TYPE=Release
cmake --build build/release
```

## Code Standards

- Follow PEP 8 for Python code.
- Use `ruff` for linting.
- Ensure type safety with `mypy`.
- Include unit tests for all new features.

## Local Continuous Integration (CI) Checks

The CI pipeline runs a series of blocking checks. Before submitting a PR, ensure you can pass these locally:

```bash
# Blocking lint check
python -m ruff check \
  fhir4ds/cli \
  fhir4ds/dqm \
  fhir4ds/sources

# Blocking pytest gate
python -m pytest \
  fhir4ds/cli/tests \
  fhir4ds/dqm \
  fhir4ds/sources \
  fhir4ds/cql/tests/unit \
  fhir4ds/viewdef
```

### DQM Conformance & Benchmarks

CI checks out the DQM conformance fixture as a submodule. If you are working on DQM evaluations, initialize the submodule:

```bash
git submodule update --init tests/data/ecqm-content-qicore-2025
```

You can generate a local DQM performance report to check for regressions:

```bash
python3 conformance/scripts/run_dqm.py
python3 benchmarks/runner/dqm_perf_report.py \
  --current conformance/reports/dqm_report.json \
  --baseline benchmarks/baselines/dqm_2025.json \
  --output-json benchmarks/output/dqm-performance-report.json \
  --output-md benchmarks/output/dqm-performance-report.md
```

For more details on GitHub Actions workflows and baseline update policies, see `.github/CI.md`.
