"""D13 SKEPTIC v0.0.26 — serve connection-contract regression (QA-D13S-001).

``create_app(connection=<non-connection>)`` leaked a raw
``AttributeError: 'str' object has no attribute 'execute'`` deep in
``ensure_schema`` — the exact QA-D8H-003 (config) / QA-D11E-001
(cql-server config) sibling class that the INV-8 typed-wrap doctrine
requires at every public server-construction boundary. A closed
connection must also surface an actionable closed-connection message,
mirroring the ``fhir4ds.register`` wrap pattern.
"""

from __future__ import annotations

import pytest


class TestServeCreateAppConnectionContract:
    def test_str_connection_raises_type_error(self):
        from fhir4ds.serve.app import create_app

        with pytest.raises(TypeError, match="connection"):
            create_app(connection="file.db")

    def test_int_connection_raises_type_error(self):
        from fhir4ds.serve.app import create_app

        with pytest.raises(TypeError, match="connection"):
            create_app(connection=42)

    def test_closed_connection_names_the_closed_state(self):
        import duckdb

        from fhir4ds.serve.app import create_app

        closed = duckdb.connect()
        closed.close()
        with pytest.raises(duckdb.ConnectionException, match="closed"):
            create_app(connection=closed)
