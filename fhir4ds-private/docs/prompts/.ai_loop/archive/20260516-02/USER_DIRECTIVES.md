# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal
Make every CQL expression/library supported by the Python translator executable in DuckDB-WASM using only C++ DuckDB extensions and SQL macros. Generate an emitted-function inventory, close all Python-only UDF gaps or replace them with SQL macros, remove Python shadowing for C++ conflicts only after parity tests pass, and add a strict translate-and-execute no-Python WASM gate.

## Pipeline
1. feature_design
2. feature_implementation
3. code_review
4. evolution (at least 5)

## Feature Plan
Any CQL expression/library supported by the translator can run in WASM using only C++ DuckDB extensions and SQL macros.

## Focus Areas
- For release 0.0.6
- Complete parity between C++ and python DuckDB extensions
- C++ DuckDB extensions should work without python extensions for fallback (no-Python WASM gate)
- All unit tests must be passing
- No regressions in any conformance tests (FHIRPath, CQL, SQL-on-FHIR, and DQM all at 100%)