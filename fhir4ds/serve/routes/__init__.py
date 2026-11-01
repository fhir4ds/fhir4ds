"""HTTP route modules for the serve surface.

Every module exports ``router``. :data:`ROUTERS` is the registration order used
by :func:`fhir4ds.serve.app.create_app`; the order also determines the order
operations appear in the derived CapabilityStatement.
"""

from __future__ import annotations

from . import capability, health, library, viewdefinition

ROUTERS = (
    health.router,
    capability.router,
    library.router,
    viewdefinition.router,
)

__all__ = ["ROUTERS", "capability", "health", "library", "viewdefinition"]
