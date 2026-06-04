"""Public API checks for the FHIR $cql facade."""

from __future__ import annotations

import fhir4ds
import fhir4ds.cql as cql


def test_facade_exports_are_discoverable():
    assert hasattr(cql, "handle_cql_operation")
    assert hasattr(cql, "CQLServerConfig")
    assert hasattr(fhir4ds, "handle_cql_operation")
    assert hasattr(fhir4ds, "create_cql_http_server")
