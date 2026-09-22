"""fhirpath_eval capability: evaluate a FHIRPath expression on one resource."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..envelopes import _EnvelopeFields
from ..errors import diagnostic_from_exception


@dataclass(frozen=True)
class FhirpathResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    results: list[Any] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["results"] = list(self.results)
        return out


def fhirpath_eval(expression: str, resource: dict[str, Any]) -> FhirpathResult:
    """Evaluate a FHIRPath expression against one FHIR resource.

    Engine seam: fhir4ds.fhirpath (the core evaluator). Results are
    JSON-serializable values.
    """
    if not isinstance(expression, str) or not expression.strip():
        from ..errors import input_error

        return FhirpathResult(
            ok=False,
            diagnostics=(input_error("expression must be a non-empty string"),),
        )
    if not isinstance(resource, dict):
        from ..errors import input_error

        return FhirpathResult(
            ok=False,
            diagnostics=(input_error("resource must be a JSON object"),),
        )
    try:
        from fhir4ds.fhirpath import evaluate

        raw = evaluate(resource, expression)
        results = [_json_safe(v) for v in (raw or [])]
    except Exception as exc:
        return FhirpathResult(
            ok=False,
            diagnostics=(diagnostic_from_exception(exc, context="fhirpath"),),
        )
    return FhirpathResult(results=results)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return json.loads(json.dumps(value, default=str))
