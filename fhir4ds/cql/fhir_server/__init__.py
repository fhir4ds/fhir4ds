"""Narrow FHIR R4 ``$cql`` facade for CQL test runner conformance."""

from .app import create_http_server, serve
from .operations import handle_cql_operation
from .types import CQLResultMetadata, CQLServerConfig, CQLTypeRef, CQLEvaluationResult

__all__ = [
    "CQLEvaluationResult",
    "CQLResultMetadata",
    "CQLServerConfig",
    "CQLTypeRef",
    "create_http_server",
    "handle_cql_operation",
    "serve",
]
