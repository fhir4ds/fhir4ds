"""Liveness endpoint.

Deliberately dependency-free: it must answer even while an operation holds the
DuckDB lock, so orchestrators can distinguish "busy" from "down". It only reads
the flush counters, which live behind their own (brief) lock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["service"])

_API_DOCS_HTML = Path(__file__).resolve().parent.parent / "static" / "api-docs.html"


@router.get("/health", summary="Liveness probe")
def health(request: Request) -> dict[str, Any]:
    """``{"status": "ok"}`` plus publication state when writes are enabled."""
    payload: dict[str, Any] = {"status": "ok"}
    context = getattr(request.app.state, "serve", None)
    flusher = getattr(context, "flusher", None) if context is not None else None
    if flusher is not None:
        payload.update(flusher.health())
    # Rehydration outcome: an operator must be able to see that a restart
    # lost rows (corrupt part) or served a fresh log (unreachable dataset)
    # instead of discovering it as silently missing resources.
    if context is not None:
        if getattr(context, "rehydrate_error", None):
            payload["rehydrate_error"] = context.rehydrate_error
        skipped = int(getattr(context, "rehydrate_skipped_parts", 0) or 0)
        if skipped:
            payload["rehydrate_skipped_parts"] = skipped
    return payload


@router.get("/api-docs", summary="This server's API documentation", response_class=HTMLResponse)
def api_docs() -> HTMLResponse:
    """Self-hosted, executable documentation (open access, same-origin)."""
    return HTMLResponse(_API_DOCS_HTML.read_text(encoding="utf-8"))
