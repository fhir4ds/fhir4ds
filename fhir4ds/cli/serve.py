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
        "--data-root",
        metavar="DIR",
        help="Directory that operation 'source' parameters may name as a path. "
        "Omit to disable path sources (containers mount data here, e.g. "
        "--data-root /data)",
    )
    parser.add_argument(
        "--no-cql-facade",
        action="store_true",
        help="Do not mount the FHIR $cql conformance facade at /fhir/$cql",
    )
    parser.add_argument(
        "--publish-dir",
        default="fhir4ds-publish",
        help="Directory holding the append-only dataset tree and the Hub cache "
        "(default: ./fhir4ds-publish)",
    )
    parser.add_argument(
        "--publish-backend",
        default="local",
        choices=("local", "hf"),
        help="Where flushed writes are published: a local directory (default) or "
        "the Hugging Face dataset repository (requires the [hf] extra and HF_TOKEN "
        "in the environment)",
    )
    parser.add_argument(
        "--publish-repository",
        help="owner/name of the dataset repository for --publish-backend hf",
    )
    parser.add_argument(
        "--publisher",
        default="fhir4ds-serve",
        help="Publisher identity written under publishers/<name>/ (default: fhir4ds-serve)",
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
    parser.add_argument(
        "--log-config",
        metavar="PATH",
        help="uvicorn logging configuration (JSON/YAML/INI). The container "
        "passes one that writes to stdout instead of uvicorn's default stderr",
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
        data_root=args.data_root,
        cql_facade=not args.no_cql_facade,
        publish_dir=args.publish_dir,
        publish_backend=args.publish_backend,
        publish_repository=args.publish_repository,
        publisher=args.publisher,
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
            loaded = load_resources(context, Path(args.resources))
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
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=args.log_level,
        log_config=getattr(args, "log_config", None),
    )
    return 0


def load_resources(context, path: Path) -> int:
    """Load FHIR data into the versioned log (phase 3 preload).

    The loader writes to a plain table, so it fills a scratch table and the rows
    are then appended through the writer — every preloaded resource gets a
    ``_seq`` like any other write, and is published with the first flush.
    """
    import json

    from fhir4ds.cql.loader import FHIRDataLoader

    connection = context.connection
    scratch = "serve_import"
    results = []
    with context.lock:
        loader = FHIRDataLoader(connection, table_name=scratch)
        loader.load_directory(path) if path.is_dir() else loader.load_file(path)
        rows = connection.execute(f"SELECT resource FROM {scratch}").fetchall()
        connection.execute(f"DROP TABLE {scratch}")
        payload = [
            {"resource": json.loads(row[0]) if isinstance(row[0], str) else row[0]}
            for row in rows
        ]
        # Skip-if-present (dataset wins): anything the rehydrated log already
        # holds — including tombstoned ids — keeps its published version; a
        # blanket re-import would resurrect deletes and write a duplicate part
        # on every restart.
        from fhir4ds.serve.versioning import BASE_TABLE

        present = {
            (resource_type, resource_id)
            for resource_type, resource_id in connection.execute(
                f"SELECT DISTINCT resourceType, id FROM {BASE_TABLE}"
            ).fetchall()
        }
        absent = [
            entry
            for entry in payload
            if (entry["resource"].get("resourceType"), entry["resource"].get("id"))
            not in present
        ]
        results = context.writer.import_rows(absent)
        # The loader's resolve() macro was bound to the scratch table; rebind it
        # to the ``resources`` view (CREATE TABLE IF NOT EXISTS is a no-op there).
        FHIRDataLoader(connection, table_name=context.config.source_table)

    # Publish OUTSIDE the context lock: the flusher's definition provider
    # re-acquires it, so flushing under the lock would deadlock.
    # A preload is a write: one synchronous flush publishes the whole seed as
    # a single part — the background tick would otherwise commit 50 rows at a
    # time — and on failure the rows stay buffered for the tick.
    flusher = getattr(context, "flusher", None)
    if flusher is not None and results:
        flusher.enqueue(
            [result.publish_row for result in results if result.publish_row]
        )
        try:
            flusher.flush()
        except Exception as exc:  # noqa: BLE001 - rows stay buffered for the tick
            print(f"fhir4ds serve: seed publish deferred to flush tick: {exc}", file=sys.stderr)
    return len(results)


__all__ = ["configure_parser", "run", "build_config", "load_resources"]
