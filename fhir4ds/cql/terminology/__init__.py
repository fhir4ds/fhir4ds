"""Terminology service abstraction (Phase 1 of the medterm4ds integration).

Public exports:
    * :class:`TerminologyEndpoint` — structural Protocol for adapters.
    * :class:`CodeRef` — normalized code reference dataclass.
    * :class:`SearchResult` — ranked discovery result dataclass.
    * :class:`TerminologyConfig` — config dataclass for the factory.
    * :func:`get_terminology_endpoint` — env-driven factory.

Zero-dependency guarantee (INV-1):
    Importing this package MUST NOT pull ``httpx`` or ``medterm4ds``.
    The adapter modules are imported lazily inside the factory body.
    Do NOT add ``from .http_adapter import ...`` (or in_process_adapter)
    to this file — that would defeat the isolation contract.

Phase 1 scope:
    This package adds the abstraction and a fallback hook on
    :class:`~fhir4ds.cql.dependency.resolver.DependencyResolver`. Public
    top-level plumbing through ``evaluate_measure`` and the FHIR ``$cql``
    facade is deferred to Phase 1.5.
"""

from __future__ import annotations

from .endpoint import TerminologyEndpoint
from .factory import get_terminology_endpoint
from .types import CodeRef, SearchResult, TerminologyConfig

# Phase 3: closure-table builder. Imported lazily-safe — closure.py only
# imports stdlib + fhir4ds internal modules (no httpx, no medterm4ds).
from .closure import (
    ClosureReport,
    build_closure_table,
    clear_closure_table,
    set_closure_loaded,
)

__all__ = [
    "TerminologyEndpoint",
    "CodeRef",
    "SearchResult",
    "TerminologyConfig",
    "get_terminology_endpoint",
    # Phase 3 (medterm4ds subsumption)
    "ClosureReport",
    "build_closure_table",
    "clear_closure_table",
    "set_closure_loaded",
]
