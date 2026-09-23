"""compare_evidence capability: delta between two evidence runs (stateless).

Realizes capability #10 of the core-ten matrix (studio FDD F10 delta
view; agentic-verify FDD D7 semantics: "N patients moved X→Y"). Both
inputs are ALREADY-EVALUATED evidence payloads — no conn, no dataset:

* the ``EvidenceResult.to_dict`` envelope (single patient), or
* a per-patient collection: ``{"patients": {pid: {"populations": {...}}}}``
  or a bare ``{pid: {"populations": {...}}}`` map.

Everything else is a typed ``input_error`` listing the found shape.
Classification per (patient, column) difference:

- ``moved``   — patient present on both sides, value changed true/false
- ``added``   — patient or column only on the current side
- ``removed`` — patient or column only on the baseline side
- ``flipped`` — value changed between null and a boolean

Result ordering is deterministic: patients sorted, then columns sorted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..envelopes import DiagnosticCode, Diagnostics, _EnvelopeFields


@dataclass(frozen=True)
class CompareEvidenceResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    changed: bool = False
    summary: dict[str, int] = field(default_factory=dict)
    patients: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out.update(
            {
                "changed": self.changed,
                "summary": dict(self.summary),
                "patients": [dict(p) for p in self.patients],
            }
        )
        return out


def _populations_of_single(payload: dict[str, Any]) -> dict[str, bool | None] | None:
    """Populations map from a single-patient EvidenceResult envelope.

    Null values are PRESERVED (uncertainty domain) — the flipped
    classification depends on bool ↔ null transitions.
    """
    pops = payload.get("populations")
    if not isinstance(pops, dict):
        return None
    out: dict[str, bool | None] = {}
    for k, v in pops.items():
        if isinstance(v, bool) or v is None:
            out[str(k)] = v
        else:
            return None
    return out


def evidence_payload_from_dict(payload: Any, *, label: str) -> dict[str, dict[str, bool | None]]:
    """Strict coercion of one evidence payload to {patient: {column: bool}}.

    Accepted shapes (exact, no duck typing):
    1. EvidenceResult envelope (has patient_id + populations dict).
    2. Collection envelope: {"patients": {pid: {"populations": {...}}}}.
    3. Bare map: {pid: {"populations": {...}}} (every value an object
       with a populations dict).

    Anything else raises ValueError with a shape-describing message.
    """
    if not isinstance(payload, dict):
        raise ValueError(
            f"{label}: expected a JSON object, got {type(payload).__name__}"
        )
    if isinstance(payload.get("populations"), dict) and (
        "patient_id" in payload
    ):
        pops = _populations_of_single(payload)
        if pops is None:
            raise ValueError(
                f"{label}: 'populations' must map column -> bool|null"
            )
        pid = str(payload.get("patient_id") or "")
        if not pid:
            raise ValueError(f"{label}: single-patient envelope lacks patient_id")
        return {pid: pops}

    inner = payload.get("patients") if isinstance(payload.get("patients"), dict) else None
    if inner is not None:
        return _coerce_patient_map(inner, label)
    # Bare map heuristic is only valid when EVERY value carries populations
    if payload and all(
        isinstance(v, dict) and isinstance(v.get("populations"), dict)
        for v in payload.values()
    ):
        return _coerce_patient_map(payload, label)

    found = (
        f"keys={sorted(payload.keys())[:6]}" if payload else "empty object"
    )
    raise ValueError(
        f"{label}: unrecognized evidence payload shape ({found}). Expected "
        "an EvidenceResult envelope or a per-patient populations map."
    )


def _coerce_patient_map(
    inner: dict[str, Any], label: str
) -> dict[str, dict[str, bool | None]]:
    out: dict[str, dict[str, bool | None]] = {}
    for pid, entry in inner.items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"{label}: patients[{pid!r}] must be an object with "
                "'populations'"
            )
        pops = _populations_of_single(entry)
        if pops is None:
            raise ValueError(
                f"{label}: patients[{pid!r}].populations must map "
                "column -> bool|null"
            )
        out[str(pid)] = pops
    return out


def compare_evidence(
    baseline: Any,
    current: Any,
    *,
    output_columns: dict[str, str] | None = None,
) -> CompareEvidenceResult:
    """Population-membership delta between two evidence payloads.

    ``baseline``/``current``: EvidenceResult envelope(s), collection
    envelopes, or per-patient maps (see ``evidence_payload_from_dict``).
    ``output_columns`` optionally maps column aliases (result keys use
    the alias when present). Failures yield typed diagnostics
    (input_error); an empty diff yields ``changed=False`` with an empty
    patients tuple and zeroed summary.
    """
    try:
        base_map = evidence_payload_from_dict(baseline, label="baseline")
        cur_map = evidence_payload_from_dict(current, label="current")
    except ValueError as exc:
        return CompareEvidenceResult(
            ok=False,
            diagnostics=(
                Diagnostics(
                    code=DiagnosticCode.INPUT_ERROR,
                    message=str(exc),
                    detail="compare_evidence input parsing",
                ),
            ),
        )

    alias = output_columns or {}
    diffs: list[dict[str, Any]] = []
    summary = {"moved": 0, "added": 0, "removed": 0, "flipped": 0}
    for pid in sorted(set(base_map) | set(cur_map)):
        base_pops = base_map.get(pid)
        cur_pops = cur_map.get(pid)
        for col in sorted(set(base_pops or {}) | set(cur_pops or {})):
            display = alias.get(col, col)
            b = base_pops.get(col) if base_pops else None
            c = cur_pops.get(col) if cur_pops else None
            b_present = base_pops is not None and col in base_pops
            c_present = cur_pops is not None and col in cur_pops
            if b_present and c_present:
                if b == c:
                    continue
                kind = "moved"
            elif c_present:
                kind = "added"
            else:
                kind = "removed"
            # null ↔ bool transitions are "flipped" (uncertainty change)
            if b_present and c_present and (
                b is None or c is None
            ) and not (b is None and c is None):
                kind = "flipped"
            summary[kind] += 1
            diffs.append(
                {
                    "patient_id": pid,
                    "column": display,
                    "classification": kind,
                    "from": b if b_present else None,
                    "to": c if c_present else None,
                    "rationale": _rationale(kind, display),
                }
            )
    return CompareEvidenceResult(
        changed=bool(diffs),
        passed=not diffs,
        summary=summary,
        patients=tuple(diffs),
    )


def _rationale(kind: str, column: str) -> str:
    if kind == "moved":
        return f"population membership changed in {column}"
    if kind == "added":
        return f"patient entered {column} (absent from baseline)"
    if kind == "removed":
        return f"patient left {column} (absent from current)"
    return f"evaluation certainty changed for {column} (null <-> bool)"
