"""Top-level fhir4ds command-line interface."""

from __future__ import annotations

import argparse

from . import cql_server, dqm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fhir4ds")
    subparsers = parser.add_subparsers(dest="command")

    dqm_parser = subparsers.add_parser("dqm", help="Run digital quality measures")
    dqm.configure_parser(dqm_parser)

    cql_server_parser = subparsers.add_parser(
        "cql-server",
        help="Serve the local FHIR $cql conformance facade",
    )
    cql_server.configure_parser(cql_server_parser)

    args = parser.parse_args(argv)
    if args.command == "dqm":
        return dqm.run(args)
    if args.command == "cql-server":
        return cql_server.run(args)

    parser.print_help()
    return 2
