"""Workspace discovery: scan configured dirs into a WorkspaceSnapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DevServerConfig

CQL_SUFFIX = ".cql"
NDJSON_SUFFIXES = (".ndjson", ".json")


@dataclass
class LibraryFile:
    """One discovered CQL library file."""

    path: Path
    name: str  # library name from the `library` declaration
    text: str
    parse_ok: bool = True
    error: str | None = None
    definitions: tuple[str, ...] = ()
    # S30: `library X version 'v'` — disks rows show a VERSION badge in
    # the nav (replacing the old "on disk" provenance chip).
    version: str | None = None

    def library_text(self) -> Any:
        from fhir4ds.operations.envelopes import LibraryText

        return LibraryText(name=self.name, text=self.text)


@dataclass
class WorkspaceSnapshot:
    """Immutable view of the discovered workspace."""

    libraries: list[LibraryFile] = field(default_factory=list)
    valuesets: list[Path] = field(default_factory=list)
    measures: list[Path] = field(default_factory=list)
    datasets: list[Path] = field(default_factory=list)
    views: list[Path] = field(default_factory=list)
    data_changed_hint: bool = False  # new/removed data file since last snapshot

    def library(self, name: str) -> LibraryFile | None:
        for lib in self.libraries:
            if lib.name == name:
                return lib
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "libraries": [
                {
                    "name": lib.name,
                    "path": str(lib.path),
                    "version": lib.version,
                    "parse_ok": lib.parse_ok,
                    "error": lib.error,
                    "definitions": list(lib.definitions),
                }
                for lib in self.libraries
            ],
            # S22a: valuesets report {path, id} — the FHIR resource `id`
            # when the file parses (drawers label disk rows by resource
            # identity, not file stem; malformed files fall back to stem).
            "valuesets": [
                # S26 review fix: label by NAME (falling back title → id
                # → stem) — OIDs are hostile nav labels.
                {"path": str(p), **_valueset_label(p)} for p in self.valuesets
            ],
            # S26 (slice 3): measures ship the RESOURCE body (parsed)
            # alongside the path — the connected app adopts disk Measures
            # (showcase workspaces carry real eCQM Measures); malformed
            # files fall back to path-only.
            "measures": [
                {"path": str(p), "resource": _measure_resource(p)}
                for p in self.measures
            ],
            "datasets": [str(p) for p in self.datasets],
            "views": [str(p) for p in self.views],
            # S30: ViewDefinition label/version metadata for nav badges.
            "view_meta": [
                {"path": str(p), **_view_label(p)} for p in self.views
            ],
            "data_changed_hint": self.data_changed_hint,
        }


def _valueset_id(path: Path) -> str | None:
    """FHIR `id` of a disk ValueSet file, or None when unreadable.

    Kept lenient by design (discovery never crashes on malformed files);
    callers treat None as "label by file stem".
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            resource = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    rid = resource.get("id") if isinstance(resource, dict) else None
    if isinstance(rid, str) and rid.strip():
        return rid.strip()
    return None


def _valueset_label(path: Path) -> dict[str, str | None]:
    """Display label parts for a disk ValueSet (S26 review fix).

    Returns {id, name, title}: `name` preferred, then `title`, then the
    `id` (OID) — the app labels rows by the first non-empty of
    name → title → id → stem.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            resource = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {
            "id": None,
            "name": None,
            "title": None,
            "version": None,
            "url": None,
        }
    if not isinstance(resource, dict):
        return {
            "id": None,
            "name": None,
            "title": None,
            "version": None,
            "url": None,
        }

    def _clean(v: object) -> str | None:
        return v.strip() if isinstance(v, str) and v.strip() else None

    return {
        "id": _clean(resource.get("id")),
        "name": _clean(resource.get("name")),
        "title": _clean(resource.get("title")),
        "version": _clean(resource.get("version")),
        # S31: canonical URL — the client seeds its workspace-URL set from
        # disk so disk-backed valuesets are never "unresolved".
        "url": _clean(resource.get("url")),
    }


def _view_label(path: Path) -> dict[str, str | None]:
    """Display label parts for a disk ViewDefinition (S30 nav badges).

    Returns {id, name, title, version}: rows label by name → title →
    id → stem and show the resource version when present.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            resource = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {
            "id": None,
            "name": None,
            "title": None,
            "version": None,
            "url": None,
        }
    if not isinstance(resource, dict):
        return {
            "id": None,
            "name": None,
            "title": None,
            "version": None,
            "url": None,
        }

    def _clean(v: object) -> str | None:
        return v.strip() if isinstance(v, str) and v.strip() else None

    return {
        "id": _clean(resource.get("id")),
        "name": _clean(resource.get("name")),
        "title": _clean(resource.get("title")),
        "version": _clean(resource.get("version")),
    }


def _measure_resource(path: Path) -> dict[str, Any] | None:
    """Parsed Measure resource at the path (S26 slice 3), or None.

    Lenient like _valueset_id — malformed files fall back to path-only.
    The Measure/expected/ subtree is EXCLUDED by the files() skip set,
    so only real Measure resources land here.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            resource = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(resource, dict) and resource.get("resourceType") == "Measure":
        return resource
    return None


def _library_name(text: str, path: Path) -> str:
    """Extract the library name from the `library <name>` declaration.

    Falls back to the file stem so malformed files still appear in the
    workspace with a stable identity (their parse_ok=False status carries
    the error to the UI).
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("library "):
            token = stripped[len("library "):].split()
            if token:
                name = token[0]
                # `library X version '...'` -> X; quoted names unlikely but
                # tolerated by stripping quotes.
                return name.strip("'\"")
        if stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
            break  # first non-comment line that isn't a library decl
    return path.stem


def _library_version(text: str) -> str | None:
    """`library X version 'v'` version token, or None."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("library "):
            parts = stripped.split()
            for i, tok in enumerate(parts):
                if tok == "version" and i + 1 < len(parts):
                    return parts[i + 1].strip("'\"") or None
            return None
        if stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
            break
    return None


def scan_workspace(cfg: DevServerConfig) -> WorkspaceSnapshot:
    """Scan all configured directories (missing dirs are simply absent)."""
    libraries: list[LibraryFile] = []
    for d in cfg.cql_dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.rglob(f"*{CQL_SUFFIX}")):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except OSError as exc:
                libraries.append(
                    LibraryFile(
                        path=path,
                        name=path.stem,
                        text="",
                        parse_ok=False,
                        error=f"unreadable: {exc}",
                    )
                )
                continue
            name = _library_name(text, path)
            version = _library_version(text)
            parse_ok, error, defs = True, None, ()
            try:
                from fhir4ds.operations import parse_cql

                result = parse_cql(text)
                if not result.ok:
                    parse_ok, error = False, (
                        result.diagnostics[0].message
                        if result.diagnostics
                        else "parse failed"
                    )
                else:
                    defs = tuple(result.definition_names)
            except Exception as exc:  # malformed CQL never crashes discovery
                parse_ok, error = False, str(exc)
            libraries.append(
                LibraryFile(
                    path=path,
                    name=name,
                    text=text,
                    parse_ok=parse_ok,
                    error=error,
                    definitions=defs,
                    version=version,
                )
            )

    def files(dirs: list[Path], suffixes: tuple[str, ...]) -> list[Path]:
        out: list[Path] = []
        for d in dirs:
            if not d.is_dir():
                continue
            # S22d-1: measure dirs may be the TYPE tree (Measure/<m>/…)
            # whose inner Parameters/List/MeasureReport/ViewDefinition
            # entries are NOT Measure resources — same exclusion class
            # as the legacy `expected` store.
            skip_parts = {"expected", "Parameters", "List", "MeasureReport", "ViewDefinition"}
            for path in sorted(d.rglob("*")):
                rel_parts = path.relative_to(d).parts
                if (
                    path.is_file()
                    and path.suffix.lower() in suffixes
                    and not (set(rel_parts[:-1]) & skip_parts)
                ):
                    out.append(path)
        return out

    return WorkspaceSnapshot(
        libraries=libraries,
        valuesets=files(cfg.valueset_dirs, (".json",)),
        measures=files(cfg.measure_dirs, (".json",)),
        datasets=files(cfg.data_dirs, NDJSON_SUFFIXES),
        views=files(cfg.view_dirs, (".json",)),
    )
