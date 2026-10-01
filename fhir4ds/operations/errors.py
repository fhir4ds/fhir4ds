"""Operations-layer error taxonomy: engine errors -> diagnostic codes.

Total over the current engine typed-error surface (FDD §3.5). Codes are
stable strings; the original type name rides in ``detail`` so engine
exception evolution never breaks the code contract.
"""

from __future__ import annotations

from typing import Any

from .envelopes import DiagnosticCode, Diagnostics, ErrorLocation


class OperationError(Exception):
    """Operations-layer programming error (bad internal call shape).

    Adapters convert this to an envelope like any other failure; it never
    escapes to a client as a traceback.
    """

    def __init__(
        self,
        message: str,
        *,
        code: DiagnosticCode = DiagnosticCode.EVALUATION_ERROR,
        detail: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail
        self.cause = cause


def _location_from(exc: Any, library: str | None) -> ErrorLocation | None:
    position = getattr(exc, "position", None)
    if not position:
        return None
    try:
        line, column = int(position[0]), int(position[1])
    except (TypeError, ValueError, IndexError):
        return None
    return ErrorLocation(start_line=line, start_column=column, library=library)


def _data_from(exc: Any) -> dict | None:
    """Lift structured engine fields verbatim (FDD §3.2 second-opinion 2.2)."""
    data: dict = {}
    for attr in ("expected", "found", "symbol", "expected_type", "actual_type",
                 "feature_name", "workaround", "suggestion"):
        value = getattr(exc, attr, None)
        if value:
            data[attr] = value
    return data or None


def diagnostic_from_exception(
    exc: BaseException,
    *,
    library: str | None = None,
    context: str = "",
) -> Diagnostics:
    """Map any exception to a Diagnostics using the FDD §3.5 table.

    The mapping is total: unknown exception types land on
    EVALUATION_ERROR with the type name in ``detail``.
    """
    from fhir4ds.cql.errors import (
        CQLError,
        LexerError,
        ParseError,
        SemanticError,
        TranslationError,
        UnsupportedFeatureError,
    )

    detail_parts: list[str] = []
    if context:
        detail_parts.append(context)
    detail_parts.append(f"{type(exc).__name__}")
    message = str(exc) or type(exc).__name__

    if isinstance(exc, UnsupportedFeatureError):
        code = DiagnosticCode.UNSUPPORTED_FEATURE
    elif isinstance(exc, (ParseError, LexerError)):
        code = DiagnosticCode.PARSE_ERROR
    elif isinstance(exc, (SemanticError, TranslationError)):
        code = DiagnosticCode.TRANSLATION_ERROR
    elif isinstance(exc, CQLError):
        code = DiagnosticCode.TRANSLATION_ERROR
    else:
        try:
            from fhir4ds.cql.fhir_server.types import CQLErrorCategory, CQLFacadeError

            if isinstance(exc, CQLFacadeError):
                category_map = {
                    CQLErrorCategory.PARSE_ERROR: DiagnosticCode.PARSE_ERROR,
                    CQLErrorCategory.TRANSLATION_ERROR: DiagnosticCode.TRANSLATION_ERROR,
                    CQLErrorCategory.UNSUPPORTED_FEATURE: DiagnosticCode.UNSUPPORTED_FEATURE,
                    CQLErrorCategory.INVALID_REQUEST: DiagnosticCode.INPUT_ERROR,
                }
                code = category_map.get(exc.category, DiagnosticCode.EVALUATION_ERROR)
                message = exc.message
            else:
                code = DiagnosticCode.EVALUATION_ERROR
        except ImportError:  # pragma: no cover - facade always importable in-tree
            code = DiagnosticCode.EVALUATION_ERROR

    return Diagnostics(
        code=code,
        message=message,
        detail=": ".join(detail_parts),
        location=_location_from(exc, library),
        data=_data_from(exc),
    )


def input_error(message: str, *, detail: str | None = None) -> Diagnostics:
    return Diagnostics(code=DiagnosticCode.INPUT_ERROR, message=message, detail=detail)


def not_found(message: str, *, detail: str | None = None) -> Diagnostics:
    return Diagnostics(code=DiagnosticCode.NOT_FOUND, message=message, detail=detail)


def dataset_error(message: str, *, detail: str | None = None) -> Diagnostics:
    return Diagnostics(code=DiagnosticCode.DATASET_ERROR, message=message, detail=detail)
