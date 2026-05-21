"""Top-level fhir4ds command-line interface."""

from __future__ import annotations

import argparse

from . import dqm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fhir4ds")
    subparsers = parser.add_subparsers(dest="command")

    dqm_parser = subparsers.add_parser("dqm", help="Run digital quality measures")
    dqm.configure_parser(dqm_parser)

    args = parser.parse_args(argv)
    if args.command == "dqm":
        return dqm.run(args)

    parser.print_help()
    return 2
