"""CLI for FHIR resource validation aligned with the WASM workbench.

``fhir4ds validate-resource <file...>`` — the workbench VALIDATOR
capability (Joel: include across surfaces).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "resources", nargs="+", help="Path(s) to JSON FHIR resource files"
    )


def run(args: argparse.Namespace) -> int:
    from fhir4ds.operations import validate_resource

    all_ok = True
    payloads = []
    for entry in args.resources:
        path = Path(entry)
        try:
            resource = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: {entry}: {exc}", file=sys.stderr)
            return 2
        result = validate_resource(resource)
        payload = result.to_dict()
        payload["source"] = str(path)
        payloads.append(payload)
        all_ok = all_ok and result.ok and result.passed is not False

    print(json.dumps(payloads if len(payloads) > 1 else payloads[0], indent=2))
    return 0 if all_ok else 1
