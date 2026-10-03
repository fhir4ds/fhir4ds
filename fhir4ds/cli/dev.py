"""`fhir4ds dev` CLI command (thin parser per CLI AGENTS)."""

from __future__ import annotations

import argparse
import sys


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "dir",
        nargs="?",
        default=".",
        help="Workspace directory (default: current directory)",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port to bind (default 8765)")
    parser.add_argument(
        "--cql-dir",
        action="append",
        default=[],
        dest="cql_dirs",
        help="Additional CQL include dir (repeatable; adds to convention+config)",
    )
    parser.add_argument(
        "--valueset-dir",
        action="append",
        default=[],
        dest="valueset_dirs",
        help="Additional ValueSet dir (repeatable)",
    )
    parser.add_argument(
        "--measure-dir",
        action="append",
        default=[],
        dest="measure_dirs",
        help="Additional measure dir (repeatable)",
    )
    parser.add_argument(
        "--data-dir",
        action="append",
        default=[],
        dest="data_dirs",
        help="Additional data dir with *.ndjson / *.json bundles (repeatable)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the browser automatically",
    )


def run(args: argparse.Namespace) -> int:
    try:
        from fhir4ds.devserver import load_config, run_dev_server

        cfg = load_config(
            args.dir,
            port=args.port,
            cql_dirs=args.cql_dirs,
            valueset_dirs=args.valueset_dirs,
            measure_dirs=args.measure_dirs,
            data_dirs=args.data_dirs,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.no_open:
        import threading
        import webbrowser

        url = f"http://{cfg.host}:{cfg.port}"
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    run_dev_server(cfg)
    return 0
