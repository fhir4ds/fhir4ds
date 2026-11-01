"""``GET /metadata`` — the FHIR CapabilityStatement.

The document is generated once at application creation from the live route
table (see :mod:`fhir4ds.serve.metadata`), so it can never drift from the
routes that actually exist.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from starlette.responses import Response

router = APIRouter(tags=["metadata"])


@router.get("/metadata", summary="Server CapabilityStatement")
def capability_statement(request: Request) -> Response:
    """Serve the CapabilityStatement built from the registered routes."""
    context = request.app.state.serve
    return Response(
        content=json.dumps(context.capability_statement, ensure_ascii=False),
        media_type="application/fhir+json",
    )
