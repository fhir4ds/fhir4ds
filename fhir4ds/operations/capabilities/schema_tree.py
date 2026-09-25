"""resource_schema_tree capability: recursive element trees for the builder.

Extends ``resource_schema`` (direct children of one type) into a full
recursive tree for the Cleanroom resource builder
(FEATURE_CLEANROOM_TEST_DATA_AUTHORING.md §3.1):

- Resource/backbone elements resolve against the translator's bundled
  R4 snapshots (``fhir4ds/cql/resources/fhir/r4/``) — same data the
  engine reads, never modified.
- Datatype children (HumanName.family, Quantity.code, Period.start, …)
  resolve against the vendored FULL datatype SDs
  (``fhir4ds/operations/resources/schemas/datatypes/``) — the resource
  snapshots are trimmed and do not carry them (ARCHITECT_REVIEW finding 1).
- Choice arms (``value[x]`` → ``valueQuantity``, …) are SYNTHESIZED from
  the element ``type`` list (finding 2), including nested choices inside
  backbones (``Observation.component.value[x]``).
- ``contentReference`` elements (``Observation.component.referenceRange`` →
  ``#Observation.referenceRange``) redirect to the referenced backbone's
  subtree (finding on path-splitting).
- Depth cap (default 4): deeper nesting exposes a JSON hatch instead of a
  form (S-3 builder doctrine).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..envelopes import DiagnosticCode, Diagnostics, _EnvelopeFields

_DEPTH_CAP_DEFAULT = 4
_PRIMITIVE_SUFFIXES = {
    "string", "code", "id", "uri", "url", "canonical", "oid", "uuid",
    "base64Binary", "boolean", "integer", "positiveInt", "unsignedInt",
    "decimal", "date", "dateTime", "instant", "time", "markdown", "xhtml",
}
# FHIRPath System.String is the string primitive on Patient.id etc.
_FHIRPATH_STRING = "http://hl7.org/fhirpath/System.String"


@dataclass(frozen=True)
class SchemaTreeResult(_EnvelopeFields):
    ok: bool = True
    passed: object = None
    diagnostics: tuple = ()
    resource_type: str = ""
    root: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        out["resource_type"] = self.resource_type
        if self.root is not None:
            out["root"] = self.root
        return out


def _datatype_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "schemas" / "datatypes"


@lru_cache(maxsize=64)
def _load_sd(kind: str, name: str) -> dict[str, Any] | None:
    """Load a StructureDefinition JSON; ``kind`` is 'resource' or 'datatype'."""
    if kind == "resource":
        from fhir4ds.cql.paths import get_resource_path

        p = get_resource_path("fhir", "r4") / f"{name}.json"
    else:
        p = _datatype_dir() / f"{name}.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=128)
def _elements_by_prefix(kind: str, sd_type: str) -> dict[str, list[dict[str, Any]]]:
    """Map 'ParentPath' -> direct-child element dicts for one SD."""
    sd = _load_sd(kind, sd_type)
    if sd is None:
        return {}
    elements = (sd.get("snapshot") or {}).get("element") or []
    out: dict[str, list[dict[str, Any]]] = {}
    for elem in elements:
        path = elem.get("path", "")
        parent = path.rsplit(".", 1)[0] if "." in path else ""
        if not parent:
            continue
        out.setdefault(parent, []).append(elem)
    return out


def _clean_type_code(code: str) -> str:
    if code == _FHIRPATH_STRING:
        return "string"
    return code


def _target_profiles(type_def: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for url in type_def.get("targetProfile", []) or []:
        if isinstance(url, str):
            tail = url.rsplit("/", 1)[-1]
            if tail and tail not in targets:
                targets.append(tail)
    return targets


def _children_of(
    context_type: str,
    parent_path: str,
    depth: int,
    depth_cap: int,
) -> list[dict[str, Any]]:
    """Recursively build child nodes for one SD context.

    ``context_type`` is the SD type ('Patient', 'HumanName', or a
    backbone pseudo-type like 'Observation.component' keyed by path).
    Resource/backbone elements live in resource SDs keyed by PATH;
    datatype elements live in datatype SDs keyed by their own prefix.
    """
    if depth >= depth_cap:
        return [{"name": "__hatch__", "hatch": True}]

    # Determine which SD set + prefix keying applies.
    is_resource_ctx = context_type in _RESOURCE_SD_NAMES
    if is_resource_ctx:
        kind = "resource"
        sd_name = context_type
    else:
        kind = "datatype"
        sd_name = context_type
    by_prefix = _elements_by_prefix(kind, sd_name)
    # Resource/backbone SDs key children by full element path prefix;
    # datatype SDs key by 'TypeName' / 'TypeName.child' prefixes too,
    # so parent_path works for both.
    elems = by_prefix.get(parent_path, [])

    nodes: list[dict[str, Any]] = []
    for elem in elems:
        path = elem.get("path", "")
        name = path[len(parent_path) + 1:] if path.startswith(parent_path + ".") else path.rsplit(".", 1)[-1]
        if not name:
            continue

        content_ref = elem.get("contentReference")
        if content_ref and content_ref.startswith("#"):
            # Redirect: children come from the referenced path's elements.
            target_path = content_ref[1:]
            redirected = by_prefix.get(target_path, [])
            if redirected:
                nodes.append(
                    _node_from_element(
                        elem, name, depth, depth_cap,
                        override_children=_build_nodes(
                            redirected, target_path, "resource", context_type,
                            depth + 1, depth_cap,
                        ),
                    )
                )
                continue

        types: list[str] = []
        reference_targets: list[str] = []
        for type_def in elem.get("type", []) or []:
            code = _clean_type_code(type_def.get("code", ""))
            if not code:
                continue
            if code not in types:
                types.append(code)
            if code == "Reference":
                for t in _target_profiles(type_def):
                    if t not in reference_targets:
                        reference_targets.append(t)

        choice = name.endswith("[x]")
        if choice:
            # Synthesize one arm per concrete type (finding 2); every arm
            # carries choice_group so adapters can render pick-one groups.
            for t in types:
                arm_suffix = t[0].upper() + t[1:]
                arm_name = name[:-3] + arm_suffix
                arm_node = _typed_node(
                    arm_name, t, reference_targets, depth, depth_cap,
                    choice_group=name,
                )
                if arm_node is not None:
                    nodes.append(arm_node)
            continue

        node = _typed_node(name, types[0] if len(types) == 1 else "", reference_targets, depth, depth_cap, elem=elem, types=types)
        if node is not None:
            nodes.append(node)
    return nodes


def _build_nodes(
    elems: list[dict[str, Any]],
    parent_path: str,
    kind: str,
    sd_context: str,
    depth: int,
    depth_cap: int,
) -> list[dict[str, Any]]:
    """Build child nodes from an explicit element list (contentReference)."""
    nodes: list[dict[str, Any]] = []
    for elem in elems:
        path = elem.get("path", "")
        name = path.rsplit(".", 1)[-1]
        if not name:
            continue
        types = [
            _clean_type_code(t.get("code", ""))
            for t in (elem.get("type") or [])
            if t.get("code")
        ]
        reference_targets: list[str] = []
        for t in elem.get("type", []) or []:
            for target in _target_profiles(t):
                if target not in reference_targets:
                    reference_targets.append(target)
        if name.endswith("[x]"):
            for t in types:
                arm_name = name[:-3] + t[0].upper() + t[1:]
                node = _typed_node(
                    arm_name, t, reference_targets, depth, depth_cap,
                    choice_group=name,
                )
                if node is not None:
                    nodes.append(node)
            continue
        node = _typed_node(
            name, types[0] if len(types) == 1 else "", reference_targets,
            depth, depth_cap, elem=elem, types=types,
        )
        if node is not None:
            nodes.append(node)
    return nodes


def _typed_node(
    name: str,
    type_code: str,
    reference_targets: list[str],
    depth: int,
    depth_cap: int,
    elem: dict[str, Any] | None = None,
    types: list[str] | None = None,
    choice_group: str | None = None,
) -> dict[str, Any] | None:
    """Build one field node; None for unsupported/unknown types."""
    node: dict[str, Any] = {"name": name}
    if choice_group:
        node["choice_group"] = choice_group
    if elem is not None:
        node["cardinality"] = f"{elem.get('min', 0)}..{elem.get('max', '1')}"
    if types:
        node["types"] = list(types)
    if type_code == "Reference":
        node["type"] = "Reference"
        node["reference_targets"] = reference_targets
        return node
    if type_code in _PRIMITIVE_SUFFIXES or type_code in ("xhtml",):
        node["type"] = type_code
        return node
    # Complex: datatype SD or backbone
    if type_code and _load_sd("datatype", type_code) is not None:
        node["type"] = type_code
        if depth + 1 >= depth_cap:
            node["children"] = [{"name": "__hatch__", "hatch": True}]
        else:
            by_prefix = _elements_by_prefix("datatype", type_code)
            child_elems = by_prefix.get(type_code, [])
            node["children"] = _build_nodes(
                child_elems, type_code, "datatype", type_code, depth + 1, depth_cap
            )
        return node
    # Backbone elements inside a resource SD (Patient.contact,
    # Observation.component): children come from the resource SD keyed
    # by the element PATH — recover it from the element itself.
    # contentReference redirects to another path's subtree first.
    if elem is not None and "." in elem.get("path", ""):
        node["type"] = "BackboneElement"
        content_ref = elem.get("contentReference")
        if content_ref and content_ref.startswith("#"):
            head = content_ref[1:].split(".", 1)[0]
            ref_elems = _elements_by_prefix("resource", head).get(
                content_ref[1:], []
            )
            node["children"] = _build_nodes(
                ref_elems, content_ref[1:], "resource", head,
                depth + 1, depth_cap,
            )
        else:
            node["children"] = _children_of_path(elem["path"], depth + 1, depth_cap)
        return node
    if type_code and _is_backbone_of(type_code, depth):
        node["type"] = "BackboneElement"
        node["children"] = _children_of_path(type_code, depth + 1, depth_cap)
        return node
    if not type_code and types:
        # Multi-type non-choice element (e.g. Resource content): expose as
        # generic object with a JSON hatch.
        node["type"] = "object"
        node["hatch"] = True
        return node
    if not type_code:
        node["type"] = "object"
        node["hatch"] = True
        return node
    # Unknown single type without an SD: hatch (extension/contained etc.)
    node["type"] = type_code
    node["hatch"] = True
    return node


def _is_backbone_of(path_like: str, depth: int) -> bool:
    """A 'Patient.contact'-shaped key is a backbone inside a resource SD."""
    head = path_like.split(".", 1)[0]
    return head in _RESOURCE_SD_NAMES


def _children_of_path(
    element_path: str, depth: int, depth_cap: int
) -> list[dict[str, Any]]:
    head = element_path.split(".", 1)[0]
    by_prefix = _elements_by_prefix("resource", head)
    elems = by_prefix.get(element_path, [])
    if depth >= depth_cap:
        return [{"name": "__hatch__", "hatch": True}]
    return _build_nodes(elems, element_path, "resource", head, depth, depth_cap)


def _node_from_element(
    elem: dict[str, Any],
    name: str,
    depth: int,
    depth_cap: int,
    override_children: list[dict[str, Any]],
) -> dict[str, Any]:
    types = [
        _clean_type_code(t.get("code", "")) for t in (elem.get("type") or []) if t.get("code")
    ]
    node: dict[str, Any] = {
        "name": name,
        "cardinality": f"{elem.get('min', 0)}..{elem.get('max', '1')}",
    }
    if types:
        node["types"] = types
        node["type"] = types[0] if len(types) == 1 else ""
    else:
        node["type"] = "BackboneElement"
    node["children"] = override_children
    return node


def _load_resource_names() -> frozenset[str]:
    from fhir4ds.cql.paths import get_resource_path

    base = get_resource_path("fhir", "r4")
    return frozenset(
        p.stem for p in base.glob("*.json") if p.stem[0].isupper()
    )


_RESOURCE_SD_NAMES: frozenset[str] = _load_resource_names()


def resource_schema_tree(
    resource_type: Any, depth: int | None = None
) -> SchemaTreeResult:
    """Recursive element tree for a FHIR R4 resource type.

    Root node children = direct resource elements; each complex child
    carries ``children`` recursively (datatype SDs + backbone chains +
    synthesized choice arms). Depth cap default 4 — at the cap a
    ``{"name": "__hatch__", "hatch": true}`` node is emitted instead of
    a form (builder opens a JSON hatch there).
    """
    if not isinstance(resource_type, str) or not resource_type.strip():
        return SchemaTreeResult(
            ok=False,
            diagnostics=(
                Diagnostics(
                    code=DiagnosticCode.INPUT_ERROR,
                    message="resource_type must be a non-empty string",
                    detail=f"got {resource_type!r}",
                ),
            ),
        )
    cap = depth if isinstance(depth, int) and depth > 0 else _DEPTH_CAP_DEFAULT
    if resource_type not in _RESOURCE_SD_NAMES:
        return SchemaTreeResult(
            ok=False,
            resource_type=resource_type,
            diagnostics=(
                Diagnostics(
                    code=DiagnosticCode.NOT_FOUND,
                    message=f"no R4 StructureDefinition shipped for {resource_type!r}",
                    detail=(
                        "the wheel bundles StructureDefinitions for the "
                        "translator's resource set; the builder offers the "
                        "shipped set plus a raw-JSON fallback"
                    ),
                ),
            ),
        )
    children = _children_of(resource_type, resource_type, 0, cap)
    return SchemaTreeResult(
        resource_type=resource_type,
        root={
            "name": resource_type,
            "type": resource_type,
            "cardinality": "0..1",
            "children": children,
        },
    )
