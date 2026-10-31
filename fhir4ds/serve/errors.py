"""FHIR ``OperationOutcome`` errors for the serve surface.

Every error response on this surface is an ``OperationOutcome`` — never a bare
JSON error body. Status codes follow the IG's error tables
(OperationDefinition-SQLQueryRun / OperationDefinition-ViewDefinitionRun):

===========  ===========================================================
400          missing/unknown/mistyped parameter, unsupported parameter
404          Library or ViewDefinition not found
422          SQL execution error, unsupported column type under _format=fhir
===========  ===========================================================

Capability envelopes carry
:class:`~fhir4ds.operations.envelopes.DiagnosticCode`; the mapping from those
codes to HTTP status lives here so the capability layer stays HTTP-free.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from fhir4ds.operations.envelopes import DiagnosticCode, Diagnostics

#: DiagnosticCode → HTTP status. Semantics:
#: * INPUT_ERROR / PARSE_ERROR / TRANSLATION_ERROR — the request itself is bad.
#: * NOT_FOUND — a referenced resource/artifact does not exist.
#: * EVALUATION_ERROR / DATASET_ERROR / UNSUPPORTED_FEATURE — the request was
#:   well formed but the server could not execute it (IG: 422).
STATUS_BY_DIAGNOSTIC_CODE: dict[DiagnosticCode, int] = {
    DiagnosticCode.INPUT_ERROR: 400,
    DiagnosticCode.PARSE_ERROR: 400,
    DiagnosticCode.TRANSLATION_ERROR: 400,
    DiagnosticCode.NOT_FOUND: 404,
    DiagnosticCode.EVALUATION_ERROR: 422,
    DiagnosticCode.DATASET_ERROR: 422,
    DiagnosticCode.UNSUPPORTED_FEATURE: 422,
    # Reserved by the operations layer and never emitted today; the HTTP
    # surface still needs a total mapping.
    DiagnosticCode.TIMEOUT: 504,
}

#: DiagnosticCode → FHIR IssueType (http://hl7.org/fhir/issue-type).
ISSUE_CODE_BY_DIAGNOSTIC_CODE: dict[DiagnosticCode, str] = {
    DiagnosticCode.INPUT_ERROR: "invalid",
    DiagnosticCode.PARSE_ERROR: "structure",
    DiagnosticCode.TRANSLATION_ERROR: "invalid",
    DiagnosticCode.NOT_FOUND: "not-found",
    DiagnosticCode.EVALUATION_ERROR: "processing",
    DiagnosticCode.DATASET_ERROR: "processing",
    DiagnosticCode.UNSUPPORTED_FEATURE: "not-supported",
    DiagnosticCode.TIMEOUT: "timeout",
}


@dataclass(frozen=True)
class Issue:
    """One ``OperationOutcome.issue`` entry."""

    code: str
    diagnostics: str
    severity: str = "error"
    expression: tuple[str, ...] = ()
    details: dict | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "severity": self.severity,
            "code": self.code,
            "diagnostics": self.diagnostics,
        }
        if self.expression:
            out["expression"] = list(self.expression)
        if self.details:
            out["details"] = self.details
        return out


class ServeError(Exception):
    """An error that becomes an ``OperationOutcome`` response."""

    def __init__(self, status_code: int, issues: Sequence[Issue]) -> None:
        if not issues:
            raise ValueError("ServeError requires at least one issue")
        super().__init__(issues[0].diagnostics)
        self.status_code = status_code
        self.issues: tuple[Issue, ...] = tuple(issues)

    @property
    def outcome(self) -> dict:
        return operation_outcome(self.issues)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.issues[0].diagnostics


def operation_outcome(issues: Iterable[Issue]) -> dict:
    """Serialize issues into a FHIR ``OperationOutcome`` resource."""
    return {
        "resourceType": "OperationOutcome",
        "issue": [issue.to_dict() for issue in issues],
    }


def bad_request(
    message: str,
    *,
    expression: Sequence[str] | None = None,
    code: str = "invalid",
) -> ServeError:
    """400 — malformed, unknown, or mistyped input."""
    return ServeError(400, [Issue(code=code, diagnostics=message, expression=tuple(expression or ()))])


def missing(message: str, *, expression: Sequence[str] | None = None) -> ServeError:
    """400 with the IG's ``required`` code (conditional parameter absent)."""
    return bad_request(message, expression=expression, code="required")


def unsupported(message: str, *, expression: Sequence[str] | None = None) -> ServeError:
    """400 with the IG's ``not-supported`` code (known but unsupported input)."""
    return bad_request(message, expression=expression, code="not-supported")


def not_found(message: str, *, expression: Sequence[str] | None = None) -> ServeError:
    """404 — a Library, ViewDefinition, or resolved dependency does not exist."""
    return ServeError(404, [Issue(code="not-found", diagnostics=message, expression=tuple(expression or ()))])


def unprocessable(
    message: str,
    *,
    expression: Sequence[str] | None = None,
    code: str = "processing",
) -> ServeError:
    """422 — well-formed request the server could not execute."""
    return ServeError(422, [Issue(code=code, diagnostics=message, expression=tuple(expression or ()))])


def from_diagnostics(diagnostics: Sequence[Diagnostics]) -> ServeError:
    """Build a :class:`ServeError` from capability diagnostics.

    The status comes from the first error-severity diagnostic; every
    diagnostic becomes an issue so compound failures keep their detail.
    """
    if not diagnostics:
        return unprocessable("The operation failed without diagnostics")
    error_items = [item for item in diagnostics if item.severity == "error"] or list(diagnostics)
    status = STATUS_BY_DIAGNOSTIC_CODE.get(error_items[0].code, 422)

    issues = []
    for item in diagnostics:
        details = dict(item.data) if item.data else None
        if item.detail:
            details = {**(details or {}), "detail": item.detail}
        issues.append(
            Issue(
                code=ISSUE_CODE_BY_DIAGNOSTIC_CODE.get(item.code, "processing"),
                diagnostics=item.message,
                severity=item.severity,
                expression=tuple(
                    [item.location.library] if item.location and item.location.library else ()
                ),
                details=details,
            )
        )
    return ServeError(status, issues)


__all__ = [
    "Issue",
    "ServeError",
    "operation_outcome",
    "bad_request",
    "missing",
    "unsupported",
    "not_found",
    "unprocessable",
    "from_diagnostics",
    "STATUS_BY_DIAGNOSTIC_CODE",
    "ISSUE_CODE_BY_DIAGNOSTIC_CODE",
]
