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
    """

    host: str = "127.0.0.1"
    port: int = 8766
    database: str = ":memory:"
    source_table: str = "resources"
    sources: Mapping[str, str] = field(default_factory=dict)
    max_rows: int = DEFAULT_MAX_ROWS
    register_udfs: bool = True
    title: str = "fhir4ds SQL-on-FHIR API"

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

    def run_locked(self, function: Any, *args: Any, **kwargs: Any) -> Any:
        """Call ``function`` while holding the connection lock."""
        with self.lock:
            return function(*args, **kwargs)


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
