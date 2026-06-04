"""CLI for the local FHIR ``$cql`` facade."""

from __future__ import annotations

import argparse
import sys

from fhir4ds.cql.fhir_server import CQLServerConfig, serve


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    parser.add_argument(
        "--base-path",
        default="/fhir",
        help="FHIR base path that also accepts $cql, for example /fhir",
    )
    parser.add_argument(
        "--python-udfs",
        action="store_true",
        help="Force Python UDF registration instead of preferring bundled native extensions",
    )
    parser.add_argument("--debug", action="store_true", help="Include diagnostics in responses")


def run(args: argparse.Namespace) -> int:
    try:
        serve(
            CQLServerConfig(
                host=args.host,
                port=args.port,
                base_path=args.base_path,
                use_cpp_extensions=not args.python_udfs,
                debug=args.debug,
            )
        )
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0
