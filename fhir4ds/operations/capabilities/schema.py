"""resource_schema capability: element metadata from FHIR R4 StructureDefinitions.

Stateless introspection over the SAME data the translator uses
(FHIRSchemaRegistry SD JSONs) — no hand-maintained field tables
(REV-002 rule). Reference targets come from the SD ``targetProfile``
slices, which the registry does not model; read directly from the
public ``get_resource_path`` seam the registry itself uses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..envelopes import DiagnosticCode, Diagnostics, _EnvelopeFields


@dataclass(frozen=True)
class ResourceSchemaResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    resource_type: str = ""
    fields: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out.update(
            {
                "resource_type": self.resource_type,
                "fields": [dict(f) for f in self.fields],
            }
        )
        return out


def _target_profiles(type_def: dict[str, Any]) -> list[str]:
    """Extract reference target resource types from a targetProfile list."""
    targets: list[str] = []
    for url in type_def.get("targetProfile", []) or []:
        if not isinstance(url, str):
            continue
        tail = url.rsplit("/", 1)[-1]
        if tail and tail not in targets:
            targets.append(tail)
    return targets


def resource_schema(resource_type: Any) -> ResourceSchemaResult:
    """Element metadata for a FHIR R4 resource type.

    Fields: name, types, cardinality (min..max), choice, reference
    targets — from the R4 StructureDefinition snapshot (direct children
    only). Unknown resource type (or SD not shipped in this wheel)
    yields ``ok=False`` with a ``not_found`` diagnostic.
    """
    from fhir4ds.cql.paths import get_resource_path

    if not isinstance(resource_type, str) or not resource_type.strip():
        return ResourceSchemaResult(
            ok=False,
            diagnostics=(
                Diagnostics(
                    code=DiagnosticCode.INPUT_ERROR,
                    message="resource_type must be a non-empty string",
                    detail=f"got {resource_type!r}",
                ),
            ),
        )
    base = get_resource_path("fhir", "r4")
    sd_path = base / f"{resource_type}.json"
    if not sd_path.exists():
        return ResourceSchemaResult(
            ok=False,
            resource_type=resource_type,
            diagnostics=(
                Diagnostics(
                    code=DiagnosticCode.NOT_FOUND,
                    message=(
                        f"no R4 StructureDefinition shipped for {resource_type!r}"
                    ),
                    detail=(
                        "the wheel bundles StructureDefinitions for the "
                        "translator's resource set; extend "
                        "fhir4ds/cql/resources/fhir/r4/ to add more"
                    ),
                ),
            ),
        )
    with open(sd_path, encoding="utf-8") as f:
        structure_def = json.load(f)
    elements = (structure_def.get("snapshot") or {}).get("element") or []
    prefix = f"{resource_type}."
    fields: list[dict[str, Any]] = []
    for elem in elements:
        path = elem.get("path", "")
        if not path.startswith(prefix) or "." in path[len(prefix):]:
            continue  # direct children only
        name = path[len(prefix):]
        if not name:
            continue  # the root element (the resource itself)
        types: list[str] = []
        reference_targets: list[str] = []
        for type_def in elem.get("type", []) or []:
            code = type_def.get("code", "")
            if not code:
                continue
            # FHIRPath System.String on Patient.id is the string primitive
            if code == "http://hl7.org/fhirpath/System.String":
                code = "string"
            if code not in types:
                types.append(code)
            if code == "Reference":
                for target in _target_profiles(type_def):
                    if target not in reference_targets:
                        reference_targets.append(target)
        fields.append(
            {
                "name": name,
                "types": types,
                "cardinality": f"{elem.get('min', 0)}..{elem.get('max', '1')}",
                "choice": "[x]" in name,
                "reference_targets": reference_targets,
            }
        )
    return ResourceSchemaResult(
        resource_type=resource_type,
        fields=tuple(fields),
    )
