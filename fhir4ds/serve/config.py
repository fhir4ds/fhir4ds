"""Configuration and per-app runtime context for the FHIR R4 HTTP surface.

``ServeConfig`` is the only user-tunable object (the CLI and ``create_app``
both build one). ``ServeContext`` bundles the config with the process-wide
runtime: one DuckDB connection, the lock that serializes access to it, and the
resource registry.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

#: Table names and source aliases are interpolated into generated SQL, so they
#: are validated structurally (never escaped by string surgery).
SQL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DEFAULT_MAX_ROWS = 100_000


def require_identifier(value: Any, *, field_name: str) -> str:
    """Validate a SQL identifier-ish config value, or raise ``ValueError``."""
    if not isinstance(value, str) or not SQL_IDENTIFIER_PATTERN.match(value):
        raise ValueError(
            f"{field_name} must be a SQL identifier "
            f"(letters, digits, underscore; not starting with a digit); got {value!r}"
        )
    return value


@dataclass(frozen=True)
class ServeConfig:
    """Runtime settings for the FHIR R4 / SQL-on-FHIR HTTP surface.

    Attributes:
        host: Bind address. Defaults to loopback: this surface executes
            author-supplied SQL by design and is not hardened for exposure.
        port: Bind port.
        database: DuckDB database path (``:memory:`` by default).
        source_table: Physical table the ViewDefinitions read. Defaults to
            ``resources`` (the :class:`~fhir4ds.cql.loader.FHIRDataLoader`
            schema).
        sources: Optional ``source`` name → DuckDB table routing. The
            operation ``source`` parameter selects one of these; an unknown
            name is rejected with 400 ``not-supported``.
        max_rows: Server-side cap for ``_limit``. Capping is not an error
            (SQL-on-FHIR v2: "Returning fewer rows ... is not treated as an
            error").
        register_udfs: Register the fhir4ds UDF surface on the connection.
        title: Service title used in the CapabilityStatement and OpenAPI docs.
        data_root: Directory that ``source`` path parameters may name. ``None``
            disables path sources entirely (only configured names resolve), so a
            mounted container opts in explicitly with ``--data-root``.
        cql_facade: Mount the FHIR ``$cql`` conformance facade at
            ``/fhir/$cql`` and advertise it in the CapabilityStatement.
        cql_max_request_bytes: Request-body cap for the ``$cql`` facade,
            mirroring ``fhir4ds.cql.fhir_server.CQLServerConfig``.
        writes_enabled: Serve the FHIR write surface and the publish store.
        publish_dir: Directory holding the dataset tree (also the Hub cache).
            ``None`` means "a throwaway directory" — the CLI always passes an
            explicit path, and tests get isolation for free.
        publish_backend: ``"local"`` (a directory, no token) or ``"hf"`` (the
            ``[hf]`` extra publishing to ``publish_repository``).
        publish_repository: ``owner/name`` of the dataset repository for the
            ``hf`` backend; also the repository the ``$bulk-publish`` manifest
            points its URLs at.
        publisher: Publisher identity written to ``publishers/<name>/``.
        flush_interval_seconds: Background flush cadence.
        flush_batch_size: Rows per background flush (``/admin/flush`` takes all).
        flush_autostart: Start the background flush thread (tests turn it off).
    """

    host: str = "127.0.0.1"
    port: int = 8766
    database: str = ":memory:"
    source_table: str = "resources"
    sources: Mapping[str, str] = field(default_factory=dict)
    max_rows: int = DEFAULT_MAX_ROWS
    register_udfs: bool = True
    title: str = "fhir4ds SQL-on-FHIR API"
    data_root: str | None = None
    cql_facade: bool = True
    cql_max_request_bytes: int = 1_000_000
    writes_enabled: bool = True
    publish_dir: str | None = None
    publish_backend: str = "local"
    publish_repository: str | None = None
    publisher: str = "fhir4ds-serve"
    flush_interval_seconds: float = 30.0
    flush_batch_size: int = 50
    flush_autostart: bool = True
    admin_key: str | None = None
    write_key: str | None = None
    key_store: str | None = None
    max_request_bytes: int = 10_000_000
    query_timeout_seconds: float = 30.0
    max_waiting_requests: int = 5
    default_limit: int = 1_000
    cors_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.host, str) or not self.host:
            raise ValueError("host must be a non-empty string")
        if not isinstance(self.port, int) or isinstance(self.port, bool):
            raise ValueError("port must be an integer")
        if not 0 <= self.port <= 65535:
            raise ValueError(f"port must be between 0 and 65535; got {self.port}")
        if not isinstance(self.database, str) or not self.database:
            raise ValueError("database must be a non-empty string")
        require_identifier(self.source_table, field_name="source_table")
        if not isinstance(self.max_rows, int) or isinstance(self.max_rows, bool):
            raise ValueError("max_rows must be an integer")
        if self.max_rows < 0:
            raise ValueError("max_rows must be >= 0")
        if not isinstance(self.sources, Mapping):
            raise ValueError("sources must be a mapping of name -> table")
        for name, table in self.sources.items():
            require_identifier(name, field_name="sources key")
            require_identifier(table, field_name=f"sources[{name!r}]")
        if self.data_root is not None and (
            not isinstance(self.data_root, str) or not self.data_root
        ):
            raise ValueError("data_root must be a non-empty string or None")
        if not isinstance(self.cql_max_request_bytes, int) or isinstance(
            self.cql_max_request_bytes, bool
        ):
            raise ValueError("cql_max_request_bytes must be an integer")
        if self.cql_max_request_bytes <= 0:
            raise ValueError("cql_max_request_bytes must be > 0")
        if self.publish_backend not in ("local", "hf"):
            raise ValueError(
                f"publish_backend must be 'local' or 'hf'; got {self.publish_backend!r}"
            )
        if self.publish_backend == "hf" and not self.publish_repository:
            raise ValueError("publish_backend='hf' requires publish_repository")
        if self.publish_dir is not None and (
            not isinstance(self.publish_dir, str) or not self.publish_dir
        ):
            raise ValueError("publish_dir must be a non-empty string or None")
        if not isinstance(self.publisher, str) or not self.publisher.strip():
            raise ValueError("publisher must be a non-empty string")
        if self.flush_interval_seconds < 0:
            raise ValueError("flush_interval_seconds must be >= 0")
        if self.flush_batch_size < 1:
            raise ValueError("flush_batch_size must be >= 1")
        for key_field in ("admin_key", "write_key"):
            value = getattr(self, key_field)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{key_field} must be a non-empty string or None")
        if self.key_store is not None and (
            not isinstance(self.key_store, str) or not self.key_store
        ):
            raise ValueError("key_store must be a non-empty string or None")
        for int_field in ("max_request_bytes", "max_waiting_requests", "default_limit"):
            value = getattr(self, int_field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{int_field} must be a positive integer")
        if not isinstance(self.cors_origins, tuple) or not all(
            isinstance(origin, str) and origin for origin in self.cors_origins
        ):
            raise ValueError("cors_origins must be a tuple of non-empty strings")
        if not isinstance(self.query_timeout_seconds, (int, float)) or isinstance(
            self.query_timeout_seconds, bool
        ):
            raise ValueError("query_timeout_seconds must be a number")
        if self.query_timeout_seconds <= 0:
            raise ValueError("query_timeout_seconds must be > 0")

    def source_table_for(self, source: str | None) -> str:
        """Resolve the ``source`` operation parameter to a physical table.

        ``None`` selects the default table. An unknown name raises ``KeyError``
        naming the configured sources so the HTTP layer can build a 400.
        """
        if source is None:
            return self.source_table
        try:
            return self.sources[source]
        except KeyError:
            raise KeyError(source) from None

    def capped_limit(self, requested: int | None) -> int | None:
        """Apply the server cap to a client-supplied ``_limit``."""
        if requested is None:
            return None
        return min(max(0, requested), self.max_rows)

    def publish_store(self) -> Any:
        """Build the publish store this configuration describes.

        ``hf`` requires the optional ``[hf]`` extra; the token is never in the
        configuration — ``huggingface_hub`` reads ``HF_TOKEN`` from the
        environment.
        """
        import tempfile

        from .store import LocalDirStore

        directory = self.publish_dir or tempfile.mkdtemp(prefix="fhir4ds-publish-")
        if self.publish_backend == "hf":
            from .hf_store import HfDatasetStore

            return HfDatasetStore(self.publish_repository or "", directory)
        return LocalDirStore(directory)


@dataclass
class ServeContext:
    """Per-application runtime: config, connection, lock, and registry.

    DuckDB is synchronous, so every route handler is a plain ``def`` and all
    connection work goes through :meth:`run_locked`.
    """

    config: ServeConfig
    connection: Any
    lock: threading.Lock = field(default_factory=threading.Lock)
    store: Any = None
    capability_statement: dict = field(default_factory=dict)
    #: Materialized path sources: table name -> resolved path (see sources.py).
    loaded_sources: dict[str, str] = field(default_factory=dict)
    #: Phase-3 write surface (None when writes are disabled).
    writer: Any = None
    flusher: Any = None

    #: API-key registry (set by create_app; None until then).
    keys: Any = None
    #: Rehydration outcome (set by create_app boot; surfaced on /health so an
    #: operator can see lost rows after a corrupt part or unreachable dataset).
    rehydrate_skipped_parts: int = 0
    rehydrate_error: str | None = None
    #: Concurrency gate bookkeeping (see run_locked).
    _gate_depth: threading.local = field(default_factory=threading.local)
    _gate: Any = None
    _gate_lock: threading.Lock = field(default_factory=threading.Lock)

    def _try_gate(self) -> bool:
        with self._gate_lock:
            if self._gate is None:
                self._gate = threading.Semaphore(
                    max(1, int(self.config.max_waiting_requests))
                )
            return self._gate.acquire(blocking=False)

    def _release_gate(self) -> None:
        with self._gate_lock:
            self._gate.release()

    def run_locked(self, function: Any, *args: Any, **kwargs: Any) -> Any:
        """Call ``function`` while holding the connection lock.

        A bounded number of requests may wait for the lock; beyond that the
        call fails fast with 503 instead of piling onto an unbounded queue.
        Reentrant calls (a locked function calling ``run_locked`` again on the
        same thread) pass through so nested helpers keep working.
        """
        from .errors import Issue, ServeError

        depth = getattr(self._gate_depth, "value", 0)
        acquired = depth == 0 and self._try_gate()
        if depth == 0 and not acquired:
            limit = max(1, int(self.config.max_waiting_requests))
            raise ServeError(
                503,
                [
                    Issue(
                        code="busy",
                        diagnostics=(
                            "server is busy; retry shortly "
                            f"(more than {limit} requests are waiting)"
                        ),
                    )
                ],
            )
        try:
            self._gate_depth.value = depth + 1
            with self.lock:
                return function(*args, **kwargs)
        finally:
            self._gate_depth.value = depth
            if acquired:
                self._release_gate()


def context_for(request: Any) -> ServeContext:
    """Return the :class:`ServeContext` bound to the application of ``request``."""
    return request.app.state.serve


__all__ = [
    "ServeConfig",
    "ServeContext",
    "context_for",
    "SQL_IDENTIFIER_PATTERN",
    "require_identifier",
    "DEFAULT_MAX_ROWS",
]
