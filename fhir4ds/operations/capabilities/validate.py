"""validate_resource capability: FHIR compliance verdict (stateless).

Reuses the loader's own validation rules so the invariant "passes
validate ⇒ loads cleanly" holds by construction: a resource accepted
here is accepted by FHIRDataLoader (identity + serialization guards).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..envelopes import DiagnosticCode, Diagnostics, _EnvelopeFields
from ..errors import diagnostic_from_exception


@dataclass(frozen=True)
class ValidateResourceResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    valid: bool = False
    resource_type: str | None = None
    resource_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out.update(
            {
                "valid": self.valid,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
            }
        )
        return out


def validate_resource(resource: Any) -> ValidateResourceResult:
    """Validate one FHIR resource against the loader's ingestion rules.

    ``passed``/``valid`` are True iff the resource would load cleanly
    through FHIRDataLoader (identity validation + strict JSON
    serialization guards incl. NaN/Infinity, lone surrogates, recursion,
    datetime/Decimal/bytes). Diagnostics carry the first violation.
    """
    from fhir4ds.cql.loader.fhir_loader import (
        _serialize_resource,
        _validate_resource_identity,
    )

    if not isinstance(resource, dict):
        return ValidateResourceResult(
            ok=False,
            diagnostics=(
                Diagnostics(
                    code=DiagnosticCode.INPUT_ERROR,
                    message="resource must be a JSON object (dict)",
                    detail=f"got {type(resource).__name__}",
                ),
            ),
        )
    try:
        resource_type, resource_id = _validate_resource_identity(resource)
        _serialize_resource(resource)
    except ValueError as exc:
        return ValidateResourceResult(
            valid=False,
            resource_type=resource.get("resourceType")
            if isinstance(resource.get("resourceType"), str)
            else None,
            resource_id=resource.get("id")
            if isinstance(resource.get("id"), str)
            else None,
            diagnostics=(
                Diagnostics(
                    code=DiagnosticCode.INPUT_ERROR,
                    message=str(exc),
                    detail="loader validation rule",
                ),
            ),
        )
    except Exception as exc:  # defensive: loader rules raise ValueError
        return ValidateResourceResult(
            ok=False,
            diagnostics=(diagnostic_from_exception(exc, context="validate_resource"),),
        )
    return ValidateResourceResult(
        valid=True,
        passed=True,
        resource_type=resource_type,
        resource_id=resource_id,
    )
