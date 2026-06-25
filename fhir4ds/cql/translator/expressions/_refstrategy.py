"""Shared types for definition-reference resolution.

Kept in a separate module so both ``_core.py`` (which emits promoted-definition
references) and the inline definition-reference branch of ``_translate_identifier``
can import without circular dependencies.

See ``ExpressionTranslator._classify_definition_ref`` for the single source of
truth that produces these strategies.
"""

from __future__ import annotations

from typing import Optional


class _RefKind:
    """How a definition reference should be resolved (kind only).

    Stored as a small class with named constants rather than an Enum so the
    hot translation path doesn't pay for Enum membership checks.
    """
    EXISTS = "exists"                   # emit EXISTS (SELECT 1 FROM "name" ...)
    CORRELATED_SCALAR = "corr_scalar"   # (SELECT sub.col FROM "name" ... LIMIT 1)
    CORRELATED_LIST = "corr_list"       # (SELECT sub.col FROM "name" ...) — no LIMIT


class _RefStrategy:
    """Resolution strategy returned by ``_classify_definition_ref``.

    ``column`` is set only for CORRELATED_SCALAR / CORRELATED_LIST.
    """
    __slots__ = ("kind", "column")

    def __init__(self, kind: str, column: Optional[str] = None):
        self.kind = kind
        self.column = column
