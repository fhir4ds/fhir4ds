"""``fhir4ds serve`` — the FHIR R4 / SQL-on-FHIR HTTP surface.

Starts a FastAPI/uvicorn server that exposes the SQL-on-FHIR v2 operations on
top of a DuckDB connection. Requires the optional ``[serve]`` extra::

    pip install "fhir4ds-v2[serve]"
    fhir4ds serve --port 8766 --resources ./fhir-data

Status lines go to stderr so stdout stays free for structured output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fhir4ds.serve.config import ServeConfig


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """Register the ``serve`` arguments."""
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1; this surface executes "
        "author-supplied SQL, so keep it on loopback)",
    )
    parser.add_argument("--port", type=int, default=8766, help="Bind port (default: 8766)")
    parser.add_argument(
        "--database",
        default=":memory:",
        help="DuckDB database path (default: :memory:)",
    )
    parser.add_argument(
        "--source-table",
        default="resources",
        help="Physical table the ViewDefinitions read (default: resources)",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="NAME=TABLE",
        help="Register a named external source routable via the operation "
        "'source' parameter (repeatable)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=100_000,
        help="Server-side cap applied to _limit (default: 100000)",
    )
    parser.add_argument(
        "--resources",
        metavar="PATH",
        help="FHIR data to load before serving: a Bundle/NDJSON file or a "
        "directory of FHIR files",
    )
    parser.add_argument(
        "--no-udfs",
        action="store_true",
        help="Do not register the fhir4ds UDFs on the connection (only useful "
        "when the database already carries them)",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="uvicorn log level (default: info)",
    )


def build_config(args: argparse.Namespace) -> ServeConfig:
    """Translate parsed arguments into a :class:`ServeConfig`."""
    sources: dict[str, str] = {}
    for entry in args.source or ():
        name, separator, table = entry.partition("=")
        if not separator or not name or not table:
            raise ValueError(f"--source expects NAME=TABLE; got {entry!r}")
        sources[name] = table
    return ServeConfig(
        host=args.host,
        port=args.port,
        database=args.database,
        source_table=args.source_table,
        sources=sources,
        max_rows=args.max_rows,
        register_udfs=not args.no_udfs,
    )


def run(args: argparse.Namespace) -> int:
    """Start the server. Returns a process exit code."""
    try:
        config = build_config(args)
    except ValueError as exc:
        print(f"fhir4ds serve: {exc}", file=sys.stderr)
        return 2

    try:
        from fhir4ds.serve.app import create_app
    except ImportError as exc:  # pragma: no cover - depends on installation
        print(
            f"fhir4ds serve requires the optional serve extra: {exc}. "
            "Install it with: pip install 'fhir4ds-v2[serve]'",
            file=sys.stderr,
        )
        return 2

    app = create_app(config)
    context = app.state.serve

    if args.resources:
        try:
            loaded = load_resources(context.connection, config.source_table, Path(args.resources))
        except Exception as exc:  # noqa: BLE001 - report and exit, never traceback
            print(f"fhir4ds serve: failed to load {args.resources}: {exc}", file=sys.stderr)
            return 2
        print(f"loaded {loaded} resources from {args.resources}", file=sys.stderr)

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on installation
        print(
            f"fhir4ds serve requires uvicorn: {exc}. "
            "Install it with: pip install 'fhir4ds-v2[serve]'",
            file=sys.stderr,
        )
        return 2

    print(
        f"fhir4ds serve listening on http://{config.host}:{config.port} "
        f"(source table: {config.source_table})",
        file=sys.stderr,
    )
    uvicorn.run(app, host=config.host, port=config.port, log_level=args.log_level)
    return 0


def load_resources(connection, table_name: str, path: Path) -> int | None:
    """Load FHIR data for the ViewDefinition tables from ``path``."""
    from fhir4ds.cql.loader import FHIRDataLoader

    loader = FHIRDataLoader(connection, table_name=table_name)
    if path.is_dir():
        return loader.load_directory(path)
    return loader.load_file(path)


__all__ = ["configure_parser", "run", "build_config", "load_resources"]
