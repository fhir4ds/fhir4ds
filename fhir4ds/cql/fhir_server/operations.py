"""FHIR ``$cql`` operation orchestration."""

from __future__ import annotations

from typing import Any

from .expression_service import evaluate_cql_request
from .parameters import error_parameters, operation_outcome, parse_cql_request
from .result_serializer import serialize_evaluation_result
from .types import CQLFacadeError, CQLErrorCategory, CQLServerConfig


def handle_cql_operation(
    body: Any,
    config: CQLServerConfig | None = None,
) -> tuple[int, dict[str, Any]]:
    """Handle a FHIR ``$cql`` operation request.

    Returns ``(status_code, response_body)`` so HTTP and tests can share the
    same operation logic.
    """
    config = config or CQLServerConfig()
    try:
        request = parse_cql_request(body)
    except CQLFacadeError as exc:
        return exc.status_code, operation_outcome(
            message=exc.message,
            category=exc.category,
            diagnostics=exc.diagnostics,
        )

    try:
        result = evaluate_cql_request(request, config)
        return 200, serialize_evaluation_result(result)
    except CQLFacadeError as exc:
        if exc.category in {
            CQLErrorCategory.PARSE_ERROR,
            CQLErrorCategory.TRANSLATION_ERROR,
            CQLErrorCategory.EVALUATION_ERROR,
            CQLErrorCategory.SERIALIZER_GAP,
            CQLErrorCategory.UNSUPPORTED_FEATURE,
        }:
            return 200, error_parameters(
                message=exc.message,
                category=exc.category,
                diagnostics=exc.diagnostics,
            )
        return exc.status_code, operation_outcome(
            message=exc.message,
            category=exc.category,
            diagnostics=exc.diagnostics,
        )
    except Exception as exc:
        return 200, error_parameters(
            message="CQL result serialization error",
            category=CQLErrorCategory.SERIALIZER_GAP,
            diagnostics=str(exc) if config.debug else None,
        )
