#!/usr/bin/env python3
"""Load selected 2025 eCQM test patients into a HAPI FHIR server."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fhir4ds.dqm.tests.conformance.cli import _discover_measures
from fhir4ds.dqm.tests.conformance.loader import load_test_suite


def put_resource(base_url: str, resource: dict) -> None:
    resource_type = resource.get("resourceType")
    resource_id = resource.get("id")
    if not resource_type or not resource_id:
        return
    url = f"{base_url.rstrip('/')}/{resource_type}/{resource_id}"
    data = json.dumps(resource).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={"Content-Type": "application/fhir+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HAPI PUT failed for {resource_type}/{resource_id}: {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure", required=True, help="Measure ID, e.g. CMS122")
    parser.add_argument("--base-url", default="http://localhost:18080/fhir")
    parser.add_argument("--suite", choices=["2025", "2026"], default="2025")
    parser.add_argument("--limit-patients", type=int, default=1)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be loaded without writing to HAPI",
    )
    args = parser.parse_args()

    configs = _discover_measures(suite=args.suite)
    measure_id = args.measure.upper()
    matches = [config for config in configs if config.id.upper() == measure_id]
    if not matches:
        available = ", ".join(config.id for config in configs[:12])
        print(f"Measure not found: {args.measure}. Available examples: {available}", file=sys.stderr)
        return 1

    config = matches[0]
    suite = load_test_suite(config)
    cases = suite.test_cases[: args.limit_patients]
    total_resources = sum(len(case.resources) for case in cases)
    print(
        f"Loading {len(cases)} patient(s), {total_resources} resource(s) "
        f"for {config.id} into {args.base_url}"
    )
    if args.dry_run:
        return 0

    for case in cases:
        for resource in case.resources:
            put_resource(args.base_url, resource)

    measure_bundle = (
        config.test_dir.parents[3]
        / "bundles"
        / "measure"
        / config.name
        / f"{config.name}-bundle.json"
    )
    print("Loaded resources.")
    print("Suggested materialization config measure entry:")
    print(
        json.dumps(
            {
                "id": config.id,
                "enabled": True,
                "path": str(measure_bundle),
                "cql": str(config.cql_path),
                "libraries": [str(path) for path in config.include_paths],
                "valuesets": [str(path) for path in config.valueset_paths],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
