"""
Entry point: python -m benchmarking.parser_audit

If cql_py is not installed as a package, set PYTHONPATH first:
    PYTHONPATH=cql-py/src python -m benchmarking.parser_audit

Or with uv (if a valid virtual environment exists):
    uv run python -m benchmarking.parser_audit
"""
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Audit the CQL corpus for parser gaps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m benchmarking.parser_audit
  python -m benchmarking.parser_audit --verbose
  python -m benchmarking.parser_audit --output benchmarking/output/cql-py/parser_audit
  python -m benchmarking.parser_audit --cql-dir /path/to/custom/cql
        """,
    )
    parser.add_argument(
        "--cql-dir",
        type=Path,
        default=None,
        help="Directory containing .cql files to audit (default: ecqm submodule cql/)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output directory for reports (default: benchmarking/output/cql-py/parser_audit/)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-file parse status as scanning progresses",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only write JSON output, skip the markdown report",
    )
    args = parser.parse_args()

    # Resolve paths
    benchmarking_dir = Path(__file__).parent.parent
    cql_dir = args.cql_dir or (
        benchmarking_dir / "data" / "ecqm-content-qicore-2025" / "input" / "cql"
    )
    output_dir = args.output or (benchmarking_dir / "output" / "parser_audit")

    if not cql_dir.exists():
        print(f"ERROR: CQL directory not found: {cql_dir}")
        print("  Run: git submodule update --init --recursive")
        sys.exit(1)

    # Import here so import errors are surfaced clearly
    from .scanner import scan_corpus
    from .categorizer import categorize
    from .reporter import build_summary, write_json, write_markdown, print_summary

    # Scan
    cql_files = sorted(cql_dir.glob("*.cql"))
    print(f"Scanning {len(cql_files)} CQL files in: {cql_dir}")
    if args.verbose:
        print()

    results = scan_corpus(cql_dir, verbose=args.verbose)

    # Categorize failures
    categories = categorize(results)

    # Build summary
    summary = build_summary(results, categories)

    # Write outputs
    json_path = write_json(summary, output_dir)
    if not args.json_only:
        md_path = write_markdown(summary, output_dir)

    # Print to stdout
    print_summary(summary)

    print(f"Reports written to: {output_dir}/")
    print(f"  {json_path.name}")
    if not args.json_only:
        print(f"  {md_path.name}")

    # Exit with non-zero if there are failures (useful for CI)
    failed = summary["totals"]["failed"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
