"""Resolution of the operation ``source`` parameter to a physical DuckDB table.

``source`` tells a SQL-on-FHIR operation where the ViewDefinition tables live.
Three shapes are understood, in this order:

``NAME`` from ``ServeConfig.sources``
    A table that already exists on the connection (``fhir4ds serve --source
    NAME=TABLE``). Nothing is loaded.

a path under ``ServeConfig.data_root``
    A directory of FHIR files or a single FHIR file, loaded **once** with the
    engine loader into ``serve_source_<digest>``. Repeated requests reuse the
    table, so the second call is a plain read. Paths outside the data root are
    refused: the root is the only part of the filesystem a request may name.

anything with a URI scheme (``hf://``, ``s3://``, …)
    Rejected with a clear ``OperationOutcome``. The Hugging Face dataset store
    (``hf://datasets/fhir4ds/bulk-publish-demo-data``) arrives in phase 3; until then
    that dataset holds no data and the surface must say so instead of crashing
    or silently querying nothing.

Resolution runs before the operation pipeline takes the connection lock, so
materialization takes the lock itself (sequentially — never nested).
"""

from __future__ import annotations

import hashlib
import pathlib
import re

from .config import ServeContext
from .errors import ServeError, not_found, unprocessable, unsupported

#: Prefix of the tables materialized from path sources.
SOURCE_TABLE_PREFIX = "serve_source_"

#: ``scheme://`` prefix of a dataset URI.
_SCHEME_PATTERN = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*)://")


def resolve_source_table(context: ServeContext, source: str) -> str:
    """Return the physical table serving ``source``.

    Raises:
        ServeError: unknown name (400), path outside the data root (400),
            unsupported scheme (400), missing path (404), or a path that
            cannot be loaded (422).
    """
    try:
        return context.config.source_table_for(source)
    except KeyError:
        pass

    scheme = _SCHEME_PATTERN.match(source)
    if scheme is not None:
        raise unsupported(
            _scheme_message(context, scheme.group("scheme"), source),
            expression=["source"],
        )

    return _resolve_path(context, source)


def _scheme_message(context: ServeContext, scheme: str, source: str) -> str:
    if scheme.lower() == "hf":
        return (
            f"Source {source!r} is a Hugging Face dataset URI, which this "
            "surface does not serve yet: the dataset store arrives in phase 3, "
            "and fhir4ds/bulk-publish-demo-data holds no data before then. "
            "No query was executed."
        )
    available = sorted(context.config.sources)
    names = ", ".join(available) if available else "none"
    return (
        f"Source {source!r} uses the {scheme}:// scheme, which this server does "
        f"not resolve. Configured source names: {names}."
    )


def _resolve_path(context: ServeContext, source: str) -> str:
    config = context.config
    if config.data_root is None:
        raise unsupported(
            f"Source {source!r} looks like a path, but local path sources are "
            "disabled on this server. Start it with --data-root <dir> to "
            "enable them.",
            expression=["source"],
        )

    root = pathlib.Path(config.data_root).expanduser().resolve()
    candidate = pathlib.Path(source).expanduser()
    path = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not path.is_relative_to(root):
        raise unsupported(
            f"Source {source!r} resolves outside the data root {root}; only "
            "paths under the root are honored.",
            expression=["source"],
        )
    if not path.exists():
        raise not_found(
            f"Source {source!r} resolves to {path}, which does not exist.",
            expression=["source"],
        )

    return _materialize(context, path)


def _materialize(context: ServeContext, path: pathlib.Path) -> str:
    """Load ``path`` into its dedicated table once, then reuse it."""
    table = SOURCE_TABLE_PREFIX + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    if table in context.loaded_sources:
        return table

    with context.lock:
        if table in context.loaded_sources:
            return table
        # The loader constructor itself issues SQL (table + resolve() macro), so
        # it must be built while the connection lock is held — DuckDB
        # connections are not safe for concurrent use.
        from fhir4ds.cql.loader import FHIRDataLoader

        loader = FHIRDataLoader(context.connection, table_name=table)
        try:
            loaded = loader.load_directory(path) if path.is_dir() else loader.load_file(path)
        except ServeError:
            raise
        except Exception as exc:  # noqa: BLE001 - boundary: every loader failure is a 422
            raise unprocessable(
                f"Source {path} could not be loaded: {exc}", expression=["source"]
            ) from exc
        if not loaded:
            raise unprocessable(
                f"Source {path} contains no FHIR resources.", expression=["source"]
            )
        context.loaded_sources[table] = str(path)

    return table


__all__ = ["SOURCE_TABLE_PREFIX", "resolve_source_table"]
