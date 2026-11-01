"""Liveness endpoint.

Deliberately dependency-free: it must answer even while an operation holds the
DuckDB lock, so orchestrators can distinguish "busy" from "down". It only reads
the flush counters, which live behind their own (brief) lock.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["service"])


@router.get("/health", summary="Liveness probe")
def health(request: Request) -> dict[str, Any]:
    """``{"status": "ok"}`` plus publication state when writes are enabled."""
    payload: dict[str, Any] = {"status": "ok"}
    context = getattr(request.app.state, "serve", None)
    flusher = getattr(context, "flusher", None) if context is not None else None
    if flusher is not None:
        payload.update(flusher.health())
    return payload
