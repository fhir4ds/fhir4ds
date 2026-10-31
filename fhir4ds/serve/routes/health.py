"""Liveness endpoint.

Deliberately dependency-free: it must answer even while an operation holds the
DuckDB lock, so orchestrators can distinguish "busy" from "down".
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["service"])


@router.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    """Return ``{"status": "ok"}`` when the process is serving."""
    return {"status": "ok"}
