# Clinical Reasoning Benchmark

A Java benchmark project for comparing the HL7/CQF clinical-reasoning Java CQL engine against FHIR4DS (DuckDB-based implementation).

## Purpose

This project benchmarks the clinical-reasoning Java engine's performance in executing CQL measures against FHIR test data. The results can be compared against DuckDB-based CQL execution to evaluate performance trade-offs.

## Setup

### Prerequisites

- Java 17 or higher
- Gradle 8.5+ (or use the included wrapper)

### Build

```bash
cd /mnt/d/duckdb-fhirpath/benchmarking/clinical-reasoning
./gradlew build
```

This will create an executable "fat JAR" at:
`build/libs/clinical-reasoning-benchmark-1.0.0-all.jar`

## Usage

```bash
cd benchmarking
java -Xmx4g -jar clinical-reasoning/build/libs/clinical-reasoning-benchmark-1.0.0-all.jar \
  --measure-dir data/ecqm-content-qicore-2025/input/tests/measure/ \
  --cql-dir data/ecqm-content-qicore-2025/input/cql/ \
  --valueset-dir data/ecqm-content-qicore-2025/input/vocabulary/valueset/external/ \
  --valueset-bundle-dir data/ecqm-content-qicore-2025/bundles/measure \
  --period-start 2026-01-01 \
  --period-end 2026-12-31 \
  --output output/clinical-reasoning/validation-run/java_comparison.json
```

### Arguments

- `--measure-dir`: Directory containing measure test data (patient subdirectories)
- `--cql-dir`: Directory containing CQL measure definition files
- `--valueset-dir`: Directory containing ValueSet definitions
- `--period-start`: Measurement period start date (yyyy-MM-dd)
- `--period-end`: Measurement period end date (yyyy-MM-dd)
- `--output`: Path to write JSON results
- `--warmup`: Number of warmup iterations (default: 0)

## Output Format

The benchmark generates a JSON file with results for each measure:

```json
[
  {
    "measure_id": "CMS165",
    "measure_name": "CMS165FHIRControllingHighBloodPressure",
    "timings": {
      "translation_ms": 3200.5,
      "total_execution_ms": 8500.2
    },
    "patients": [
      {"id": "uuid...", "elapsed_ms": 120.5, "status": "success"},
      {"id": "uuid...", "elapsed_ms": 85.3, "status": "success"}
    ],
    "summary": {
      "patient_count": 25,
      "success_count": 23,
      "error_count": 2,
      "avg_patient_ms": 95.4,
      "total_execution_ms": 8500.2
    }
  }
]
```

## Implementation Notes

- Uses `org.opencds.cqf.cql:engine:3.0.0` for CQL execution
- Uses `info.cqframework:cql-to-elm:3.0.0` for CQL-to-ELM translation
- HAPI FHIR R4 for FHIR resource parsing
- Zero-overhead filesystem-based data provider (reads JSON resources directly)
- Timing measured with `System.nanoTime()` for millisecond precision

## Architecture

- `ClinicalReasoningBenchmark`: Main CLI entry point with picocli
- `NdjsonDataProvider`: Loads FHIR resources from filesystem
- `CqlEvaluator`: Wraps CQL translation and evaluation
- `TranslationResult`/`EvaluationResult`: Result POJOs with timing data

## Test Data

The benchmark expects test data in the format provided by `data/ecqm-content-qicore-2025/`:
- Each measure has patient subdirectories (UUID-named)
- Patient directories contain individual JSON resource files or bundle files
- CQL definitions are in the cql-dir
- ValueSets are in the valueset-dir

## Limitations

- Current implementation has TODO comments for FHIR model resolver configuration
- Terminology provider is a no-op (assumes all codes are valid)
- Data provider is simplified and may not handle all FHIR resource relationships
- Error handling is basic; may need refinement for production use