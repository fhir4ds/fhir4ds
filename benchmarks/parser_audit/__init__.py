"""
Parser audit tool for the CQL corpus.

Parses every .cql file in the ecqm submodule, collects errors by construct,
and produces a ranked report of parser gaps.

Usage:
    python -m benchmarking.parser_audit              # full audit
    python -m benchmarking.parser_audit --verbose    # include per-file detail
    python -m benchmarking.parser_audit --output benchmarking/output/parser_audit
"""
