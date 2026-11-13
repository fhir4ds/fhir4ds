"""Shared terminology-endpoint errors.

Two error classes, deliberately distinguished by TYPE rather than by message
text, because callers must branch on them:

``TerminologyEndpointError``
    Any endpoint failure (transient timeouts, 5xx, connection errors, refused
    requests). Callers such as ``DependencyResolver.resolve_valueset`` may
    degrade these to a WARNING + no result under their INV-8 contract.

``TerminologyCapabilityError``
    The backend cannot serve this request AT ALL — a capability mismatch, not a
    fault. Retrying will never help. Owner ruling for AMUX-115 item 3
    (2026-11-12): these must **fail loudly to the measure author** and must
    never be silently degraded to "no codes", because that turns a
    backend-misconfiguration into criteria that quietly under-match.

Never branch on ``str(exc)`` to tell these apart; the class is the contract.
"""

from __future__ import annotations

__all__ = ["TerminologyEndpointError", "TerminologyCapabilityError"]


class TerminologyEndpointError(RuntimeError):
    """Raised when a terminology endpoint cannot satisfy a request.

    Shared by every adapter (VSAC, generic FHIR HTTP, ...) so callers can catch
    one type. Message content policy: includes the HTTP status and an
    OperationOutcome diagnostics excerpt when available, but NEVER API keys,
    credentials, or raw Authorization headers.
    """


class TerminologyCapabilityError(TerminologyEndpointError):
    """The backend cannot serve this request at all (capability mismatch).

    Raised when the endpoint rejects the *form* of the request rather than
    failing to execute it — for example a medterm4ds backend asked to expand a
    ValueSet by canonical URL, which it does not implement (it resolves only a
    POSTed body, a ``fhir_vs`` implicit URL, or a filter).

    Contract for callers that normally degrade endpoint failures: do NOT catch
    this one into a WARNING + empty result. Propagate it so the failure reaches
    the author, who can fix the configuration. Transient faults remain
    ``TerminologyEndpointError`` (or the underlying transport exception) and may
    keep the degrade path.
    """
