"""Top-level fhir4ds command-line interface."""

from __future__ import annotations

import argparse

from . import cql, cql_server, dqm, fhirpath_cli, validate_resource, verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fhir4ds")
    subparsers = parser.add_subparsers(dest="command")

    dqm_parser = subparsers.add_parser("dqm", help="Run digital quality measures")
    dqm.configure_parser(dqm_parser)

    cql_parser = subparsers.add_parser(
        "cql", help="Translate or evaluate CQL (WASM-demo-aligned surface)"
    )
    cql.configure_parser(cql_parser)

    cql_server_parser = subparsers.add_parser(
        "cql-server",
        help="Serve the local FHIR $cql conformance facade",
    )
    cql_server.configure_parser(cql_server_parser)

    fhirpath_parser = subparsers.add_parser(
        "fhirpath", help="Evaluate a FHIRPath expression against a resource"
    )
    fhirpath_cli.configure_parser(fhirpath_parser)

    validate_parser = subparsers.add_parser(
        "validate-resource", help="Validate FHIR resource JSON files"
    )
    validate_resource.configure_parser(validate_parser)

    verify_parser = subparsers.add_parser(
        "verify",
        help="Evaluate a CQL library against a dataset with optional test cases",
    )
    verify.configure_parser(verify_parser)

    args = parser.parse_args(argv)
    if args.command == "dqm":
        return dqm.run(args)
    if args.command == "cql":
        return cql.run(args)
    if args.command == "cql-server":
        return cql_server.run(args)
    if args.command == "fhirpath":
        return fhirpath_cli.run(args)
    if args.command == "validate-resource":
        return validate_resource.run(args)
    if args.command == "verify":
        return verify.run(args)

    parser.print_help()
    return 2
