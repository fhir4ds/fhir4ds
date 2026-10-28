"""CLI for FHIRPath evaluation aligned with the WASM demo capability.

``fhir4ds fhirpath <expr> --resource patient.json`` evaluates a FHIRPath
expression against a single resource — the PatientDataViewer / SDC-engine
capability.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("expression", help="FHIRPath expression to evaluate")
    parser.add_argument(
        "--resource", default=None,
        help="Path to a JSON FHIR resource (defaults to stdin)",
    )


def run(args: argparse.Namespace) -> int:
    from fhir4ds.operations import fhirpath_eval

    try:
        if args.resource:
            raw = Path(args.resource).read_text(encoding="utf-8")
        else:
            raw = sys.stdin.read()
        resource = json.loads(raw)
        if not isinstance(resource, dict):
            raise ValueError("resource must be a JSON object")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = fhirpath_eval(args.expression, resource)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 1
