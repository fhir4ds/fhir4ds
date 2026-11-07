"""FHIR R4 HTTP surface for the fhir4ds engine.

Projects existing engine capabilities as a FHIR R4 REST API:

* ``Library`` / ``ViewDefinition`` registries (``POST``/``GET``);
* SQL-on-FHIR v2 ``$sqlquery-run`` at system, type, and instance level;
* SQL-on-FHIR v2 ``$viewdefinition-run`` / ``$run`` at type and instance level;
* ``GET /metadata`` with a CapabilityStatement derived from the route table.

The layer is an adapter: it adds HTTP routing, FHIR ``Parameters`` in/out, and
format negotiation on top of `fhir4ds.sqlquery` and `fhir4ds.viewdef`, and owns
no engine logic of its own.

Importing this package does not import FastAPI: ``create_app`` is resolved
lazily so the optional ``[serve]`` extra stays optional.
"""

from __future__ import annotations

from typing import Any

from .config import ServeConfig

__version__ = "0.0.22"

__all__ = ["create_app", "ServeConfig", "__version__"]


def __getattr__(name: str) -> Any:
    """Resolve ``create_app`` lazily (FastAPI is an optional dependency)."""
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
