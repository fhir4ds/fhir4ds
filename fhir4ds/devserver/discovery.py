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
                    "parse_ok": lib.parse_ok,
                    "error": lib.error,
                    "definitions": list(lib.definitions),
                }
                for lib in self.libraries
            ],
            "valuesets": [str(p) for p in self.valuesets],
            "measures": [str(p) for p in self.measures],
            "datasets": [str(p) for p in self.datasets],
            "views": [str(p) for p in self.views],
            "data_changed_hint": self.data_changed_hint,
        }


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
                )
            )

    def files(dirs: list[Path], suffixes: tuple[str, ...]) -> list[Path]:
        out: list[Path] = []
        for d in dirs:
            if not d.is_dir():
                continue
            for path in sorted(d.rglob("*")):
                if (
                    path.is_file()
                    and path.suffix.lower() in suffixes
                    # S3b: expected-results store lives under measures/
                    # but is not a Measure resource — exclude it from
                    # measure discovery (it previously captured the saved
                    # cqfm-test-cases MeasureReports as "measures").
                    and "expected" not in path.relative_to(d).parts
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
