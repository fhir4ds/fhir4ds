"""Slice 1 backend: parameter/header editing + valueset table editing.

Server-side, zero-write doctrine: edits update the per-connection session /
in-memory buffers; files are only touched by the author's editor via Apply.
For valuesets (which live on disk as JSON and feed the kernel at load), an
Apply writes the file (workspace-owned artifact, not a dependency dir) and
flags staleness — kernel restart picks it up.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Parameter / header editing (CQL library header text surgery)
# ---------------------------------------------------------------------------

_PARAM_RE = re.compile(
    r"^[ \t]*parameter[ \t]+(?P<quoted>\"(?P<qname>[^\"]+)\"|(?P<name>[A-Za-z0-9_]+))"
    r"[ \t]+(?P<ptype>[A-Za-z][A-Za-z0-9_.]*)"
    r"(?:[ \t]+default[ \t]+(?P<default>.+?))?[ \t]*$",
    re.MULTILINE,
)


@dataclass
class ParameterInfo:
    """One `parameter` declaration extracted from a library header."""

    name: str
    type: str
    default: str | None  # raw default expression text (None = no default)
    line_start: int  # offset of line start
    line_end: int = 0  # offset just past the line (incl. newline)


def parse_parameters(text: str) -> list[ParameterInfo]:
    """Extract parameter declarations from library text (header region).

    Tolerant: malformed lines are skipped, never crash.
    """
    out: list[ParameterInfo] = []
    for m in _PARAM_RE.finditer(text):
        name = m.group("qname") or m.group("name")
        default = m.group("default")
        if default is not None:
            default = default.strip()
            if default in ('""', "''"):
                default = '""'
        out.append(
            ParameterInfo(
                name=name,
                type=m.group("ptype"),
                default=default,
                line_start=m.start(),
                line_end=m.end() + (1 if text[m.end():m.end() + 1] == "\n" else 0),
            )
        )
    return out


def _render_parameter(name: str, ptype: str, default: str | None) -> str:
    default_part = f" default {default}" if default else ""
    return f'parameter "{name}" {ptype}{default_part}'


def upsert_parameter(text: str, name: str, ptype: str, default: str | None) -> str:
    """Add or update one parameter declaration; returns new library text."""
    for info in parse_parameters(text):
        if info.name == name:
            line = _render_parameter(name, ptype, default)
            return text[: info.line_start] + line + "\n" + text[info.line_end:]
    # append after the last existing parameter (or after using/include block)
    insert_at = 0
    for info in parse_parameters(text):
        insert_at = info.line_end
    if insert_at == 0:
        # no parameters yet: insert after the last of library/using/manifest
        for m in _MANIFEST_RE.finditer(text):
            insert_at = m.end() + (1 if text[m.end():m.end() + 1] == "\n" else 0)
    return (
        text[:insert_at] + _render_parameter(name, ptype, default) + "\n" + text[insert_at:]
    )


def delete_parameter(text: str, name: str) -> str:
    """Remove one parameter declaration; returns new library text."""
    for info in parse_parameters(text):
        if info.name == name:
            return text[: info.line_start] + text[info.line_end:]
    raise ValueError(f"unknown parameter {name!r}")


_MANIFEST_RE = re.compile(
    r"^[ \t]*(?:library[ \t]+[A-Za-z0-9_]+(?:[ \t]+version[ \t]+'[^']*')?"
    r"|using[ \t]+[A-Za-z0-9_]+(?:[ \t]+version[ \t]+'[^']*')?"
    r"|include[ \t]+[A-Za-z0-9_]+(?:[ \t]+version[ \t]+'[^']*')?"
    r"[ \t]+called[ \t]+[A-Za-z0-9_]+)[ \t]*$",
    re.MULTILINE,
)


def header_info(text: str) -> dict[str, Any]:
    """Minimal header summary for the header editor pane."""
    params = parse_parameters(text)
    lib_name = None
    m = re.search(r"^[ \t]*library[ \t]+[\"']?([A-Za-z0-9_]+)", text, re.MULTILINE)
    if m:
        lib_name = m.group(1)
    includes: list[dict[str, str]] = []
    for m in _MANIFEST_RE.finditer(text):
        body = m.group(0)
        if body.strip().startswith("include "):
            im = re.match(
                r"^[ \t]*include[ \t]+([A-Za-z0-9_]+)(?:[ \t]+version[ \t]+'([^']*)')?"
                r"[ \t]+called[ \t]+([A-Za-z0-9_]+)[ \t]*$",
                body,
            )
            if im:
                includes.append(
                    {"path": im.group(1), "version": im.group(2) or "", "local": im.group(3)}
                )
    return {"library": lib_name, "includes": includes, "parameters": [p.__dict__ for p in params]}


# ---------------------------------------------------------------------------
# ValueSet table editing (JSON file surgery, workspace-owned)
# ---------------------------------------------------------------------------

@dataclass
class ValueSetEdit:
    """One staged valueset concept row edit (add/update/remove a concept)."""

    action: str  # 'add' | 'remove' | 'update'
    system: str | None = None
    code: str | None = None
    display: str | None = None
    old_code: str | None = None  # for update: the row being changed


def apply_valueset_edit(resource: dict[str, Any], edit: ValueSetEdit) -> dict[str, Any]:
    """Apply one concept edit to a ValueSet resource dict (in compose.include).

    Edits target ``compose.include[].concept[]`` — the authored terminology
    (expansion is derived output; display column is ignored for logic per
    Muse: greyed out in the UI).
    """
    compose = resource.setdefault("compose", {"include": []})
    includes = compose.get("include")
    if not isinstance(includes, list):
        raise ValueError("ValueSet.compose.include must be a list")
    if edit.action == "add":
        for inc in includes:
            if isinstance(inc, dict) and inc.get("system") == edit.system:
                concepts = inc.setdefault("concept", [])
                concepts.append({"code": edit.code, "display": edit.display})
                return resource
        # new system block
        includes.append(
            {"system": edit.system, "concept": [{"code": edit.code, "display": edit.display}]}
        )
        return resource
    if edit.action == "remove":
        for inc in includes:
            if not isinstance(inc, dict) or inc.get("system") != edit.system:
                continue
            concepts = inc.get("concept") or []
            kept = [c for c in concepts if isinstance(c, dict) and c.get("code") != edit.code]
            if len(kept) != len(concepts):
                inc["concept"] = kept
                return resource
        raise ValueError(f"concept {edit.code!r} not found in system {edit.system!r}")
    if edit.action == "update":
        for inc in includes:
            if not isinstance(inc, dict) or inc.get("system") != edit.system:
                continue
            concepts = inc.get("concept") or []
            for i, c in enumerate(concepts):
                if isinstance(c, dict) and c.get("code") == edit.old_code:
                    concepts[i] = {"code": edit.code, "display": edit.display}
                    return resource
        raise ValueError(f"concept {edit.old_code!r} not found in system {edit.system!r}")
    raise ValueError(f"unknown valueset edit action {edit.action!r}")


def validate_valueset_edit(edit: ValueSetEdit) -> list[str]:
    """Muse: validate system-URI + non-empty code on save."""
    problems: list[str] = []
    if edit.action == "add" or edit.action == "update":
        if not edit.system or not isinstance(edit.system, str) or not re.match(
            r"^https?://[^\s]+$", edit.system
        ):
            problems.append(f"system must be an absolute http(s) URI: {edit.system!r}")
        if not edit.code or not isinstance(edit.code, str) or not edit.code.strip():
            problems.append("code must be a non-empty string")
    return problems


def valueset_used_by(resource: dict[str, Any], library_texts: list[tuple[str, str]]) -> list[str]:
    """Defines referencing this valueset (by URL match in `valueset` decls).

    library_texts: [(library_name, text), ...] — scanned for
    ``valueset "X": '<url>'`` declarations whose URL equals this VS url.
    """
    url = resource.get("url")
    if not url:
        return []
    users: list[str] = []
    for lib_name, text in library_texts:
        for m in re.finditer(
            r"^[ \t]*valueset[ \t]+\"([^\"]+)\"[ \t]*:[ \t]*'([^']+)'", text, re.MULTILINE
        ):
            if m.group(2) == url:
                # collect define names referencing the valueset id
                vs_id = m.group(1)
                for dm in re.finditer(
                    rf"\b{re.escape(vs_id)}\b", text
                ):
                    users.append(f"{lib_name}.{vs_id}")
                    break
    return sorted(set(users))


def validate_valueset_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Full-resource validation via the operations layer (validate_resource)."""
    from fhir4ds.operations import validate_resource

    result = validate_resource(resource)
    return result.to_dict()
