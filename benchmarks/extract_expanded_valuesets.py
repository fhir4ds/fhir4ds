#!/usr/bin/env python3
"""
Extract expanded valuesets from bundle files and save them to a valuesets directory.

The bundles in bundles/measure/*/ contain pre-expanded valuesets with expansion.contains arrays.
"""
import json
from pathlib import Path
from collections import defaultdict

BENCHMARKS_DIR = Path(__file__).parent
TESTS_DIR = BENCHMARKS_DIR.parent / "tests"
BUNDLES_DIR = TESTS_DIR / "data" / "ecqm-content-qicore-2025" / "bundles" / "measure"
OUTPUT_DIR = TESTS_DIR / "data" / "valuesets"


def extract_valuesets_from_bundle(bundle_path: Path) -> list:
    """Extract all valuesets from a bundle file."""
    valuesets = []

    with open(bundle_path) as f:
        data = json.load(f)

    for entry in data.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "ValueSet":
            # Check if it has expansion
            if "expansion" in resource and "contains" in resource["expansion"]:
                valuesets.append(resource)

    return valuesets


def main():
    """Extract all expanded valuesets from bundle files."""
    print("Extracting expanded valuesets from bundles...")

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Track statistics
    total_valuesets = 0
    total_codes = 0
    by_measure = defaultdict(int)

    # Find all bundle files
    for measure_dir in sorted(BUNDLES_DIR.iterdir()):
        if not measure_dir.is_dir():
            continue

        measure_name = measure_dir.name
        files_dir = measure_dir / f"{measure_name}-files"

        if not files_dir.exists():
            continue

        # Find valueset bundle files
        for bundle_file in files_dir.glob("valuesets-*-bundle.json"):
            print(f"  Processing {bundle_file.name}...")

            valuesets = extract_valuesets_from_bundle(bundle_file)

            for vs in valuesets:
                vs_id = vs.get("id")
                vs_url = vs.get("url", "")

                # Save as individual file
                # Use URL as filename (safe version)
                safe_name = vs_url.replace("http://", "").replace("/", "_").replace(":", "_")
                if not safe_name:
                    safe_name = vs_id.replace(":", "_")

                output_file = OUTPUT_DIR / f"{safe_name}.json"

                with open(output_file, 'w') as f:
                    json.dump(vs, f, indent=2)

                total_valuesets += 1

                # Count codes
                codes = vs.get("expansion", {}).get("contains", [])
                total_codes += len(codes)
                by_measure[measure_name] += 1

    print(f"\nExtraction complete!")
    print(f"  Total valuesets: {total_valuesets}")
    print(f"  Total codes: {total_codes}")
    print(f"  Measures processed: {len(by_measure)}")
    print(f"\nValuesets saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
