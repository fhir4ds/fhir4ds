"""FastAPI application factory for the FHIR R4 / SQL-on-FHIR surface.

Shape of the app:

* every route handler is a plain ``def`` — DuckDB is synchronous, so an
  ``async def`` handler would block the event loop;
* one shared DuckDB connection guarded by a
  :class:`threading.Lock` (:class:`~fhir4ds.serve.config.ServeContext`);
* FHIR resources are plain dicts (no pydantic FHIR models);
* every error is a FHIR ``OperationOutcome``.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import ServeConfig, ServeContext
from .errors import Issue, ServeError
from .metadata import build_capability_statement
from .routes import ROUTERS
from .routes import cql as cql_routes
from .store import REGISTRY_TABLE, ResourceStore

logger = logging.getLogger(__name__)

FHIR_JSON = "application/fhir+json"

_DESCRIPTION = (
    "FHIR R4 HTTP surface for the fhir4ds engine. Serves SQL-on-FHIR v2 "
    "`$sqlquery-run` (Analytics Layer) and `$viewdefinition-run` / `$run` "
    "(view evaluation), with the Library and ViewDefinition registries that "
    "back them. Read/execute only: no writes beyond the definition registry."
)


def create_app(
    config: ServeConfig | None = None,
    *,
    connection: Any = None,
) -> FastAPI:
    """Build the ASGI application.

    Args:
        config: Service configuration; defaults to :class:`ServeConfig`.
        connection: Pre-built DuckDB connection. When omitted, one is created
            from ``config`` via :func:`fhir4ds.connection.create_connection`
            (which registers the fhirpath/CQL UDFs the generated SQL needs).

    Returns:
        A configured :class:`fastapi.FastAPI` instance.
    """
    from fhir4ds import __version__ as engine_version

    settings = config or ServeConfig()
    if connection is None:
        connection = _connect(settings)

    context = ServeContext(config=settings, connection=connection)
    context.store = ResourceStore(connection)
    with context.lock:
        context.store.ensure_schema()

    # Phase 3: the versioned log, the publish store, and the flush loop. Built
    # before the app so the lifespan can shut the flush thread down.
    writes_router = _configure_writes(context, settings) if settings.writes_enabled else None

    app = FastAPI(
        title=settings.title,
        version=engine_version,
        description=_DESCRIPTION,
        lifespan=_lifespan(context),
    )
    app.state.serve = context

    for router in ROUTERS:
        app.include_router(router)

    # The CQL conformance facade is mounted together with its CapabilityStatement
    # declaration, so /metadata advertises `$cql` exactly when the route exists.
    if settings.cql_facade:
        cql_routes.mount(app, settings)

    # Generic resource routes come last: FastAPI matches in registration order,
    # so /Library and /ViewDefinition (and their operations) keep winning.
    if writes_router is not None:
        app.include_router(writes_router)

    # Derived, never hand-written: walks the registered routes.
    context.capability_statement = build_capability_statement(app, title=settings.title)

    _install_error_handlers(app)
    return app


def _configure_writes(context: ServeContext, settings: ServeConfig) -> Any:
    """Create the log, the writer and the flush loop; return the writes router."""
    from . import versioning
    from .flusher import FlushManager
    from .writes import ResourceWriter
    from .writes import router as writes_router

    with context.lock:
        versioning.ensure_schema(context.connection)
        database_seq = versioning.next_seq(context.connection)

    try:
        publish_store = settings.publish_store()
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "publish_backend='hf' requires the optional hf extra: "
            "pip install 'fhir4ds-v2[serve,hf]'"
        ) from exc

    # The writer continues from whichever is further ahead: the log's own rows
    # (a database that survived a restart) or the published state (a fresh
    # in-memory database against an existing dataset).
    context.writer = ResourceWriter(
        context.connection, seq=max(database_seq, publish_store.current_seq())
    )
    context.flusher = FlushManager(
        publish_store,
        interval=settings.flush_interval_seconds,
        batch_size=settings.flush_batch_size,
        publisher=settings.publisher,
        repository=settings.publish_repository,
        request_url="/$bulk-publish",
        definition_provider=lambda: _definitions(context),
        autostart=settings.flush_autostart,
    )
    return writes_router


def _definitions(context: ServeContext) -> list[dict]:
    """Served Library/ViewDefinition resources, for the dataset's definition files."""
    rows = context.run_locked(
        lambda: context.connection.execute(
            f"SELECT body FROM {REGISTRY_TABLE} ORDER BY resource_type, id"
        ).fetchall()
    )
    return [json.loads(row[0]) for row in rows]


def _lifespan(context: ServeContext) -> Any:
    """Stop the flush thread on shutdown, publishing anything still buffered."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        try:
            yield
        finally:
            flusher = context.flusher
            if flusher is not None:
                flusher.stop()
                if flusher.pending():
                    try:
                        flusher.flush()
                    except Exception:  # noqa: BLE001 - shutdown must not raise
                        logger.exception("final flush failed")

    return lifespan


def _connect(settings: ServeConfig) -> Any:
    from fhir4ds.connection import create_connection

    return create_connection(settings.database, register_udfs=settings.register_udfs)


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServeError)
    def handle_serve_error(request: Request, exc: ServeError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.outcome,
            media_type=FHIR_JSON,
        )

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Convert framework-level body/query failures into OperationOutcomes."""
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error.get('loc', ()))}: {error.get('msg', '')}"
            for error in exc.errors()
        )
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [
                Issue(code="structure", diagnostics=detail or "Invalid request").to_dict()
            ],
        }
        return JSONResponse(status_code=400, content=outcome, media_type=FHIR_JSON)

    @app.exception_handler(Exception)
    def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        """Last resort: never leak a traceback to a FHIR client."""
        logger.exception("Unhandled error serving %s %s", request.method, request.url.path)
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [
                Issue(
                    code="exception",
                    diagnostics=f"Internal server error: {type(exc).__name__}",
                ).to_dict()
            ],
        }
        return JSONResponse(status_code=500, content=outcome, media_type=FHIR_JSON)


__all__ = ["create_app"]
