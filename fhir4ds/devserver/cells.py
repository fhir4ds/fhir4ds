"""Notebook cells: `// # %% [name: X]` markers over a plain .cql library.

Conductor-approved model (FEATURE_DEV_SERVER_V2.md, 2026-10-03):

* Cell format is jupytext-percent style comments; the same file stays a
  valid batch library (markers are CQL comments).
* Everything before the first marker is the shared HEADER (unmarked
  defines are header-included in every composition — ruling 3).
* Each cell = one ``define`` (or ``define function``). Cells are
  identified by define name (ruling 4: optional ``[name: X]`` marker
  label defaults to the define name).
* Kernel state per WS connection = a working define-set (CellSession).
  Rerun = REPLACE semantics. No cell-order discipline: the translator
  resolves topologically; dangling references fail cleanly until run.
* Run modes: ``cell`` (STRICT single-define — ruling 1), ``cell_deps``
  (refs transitive closure, ONE evaluation split per-cell via
  output_columns narrowing), ``all``, ``to_here`` (file-order prefix —
  ruling 5).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any

from fhir4ds.cql.parser import parse_cql

MARKER_RE = re.compile(r"^\s*//\s*#\s*%%(\s*\[name:\s*(?P<name>[A-Za-z0-9_]+)\s*\])?\s*$")

# Cell lifecycle statuses (see CellRecord.status).
IDLE = "idle"
RUNNING = "running"
OK = "ok"
ERROR = "error"
STALE = "stale"


@dataclass
class ParsedCell:
    """One cell extracted from a marked-up library text."""

    name: str  # define name (marker label overrides when present)
    label: str | None  # explicit [name: X] label, if any
    text: str  # the cell's CQL body (define ...)
    order: int  # file order index among cells
    is_function: bool = False


@dataclass
class ParsedLibrary:
    """Marker split of one library text."""

    header: str  # everything before the first marker (includes using/...)
    cells: list[ParsedCell] = field(default_factory=list)
    error: str | None = None  # marker-level problems (duplicate names...)


def split_cells(text: str) -> ParsedLibrary:
    """Split a library text into header + cells on ``// # %%`` markers.

    Duplicate define names across cells are a split error (cell identity
    is the define name; duplicates would be ambiguous).
    """
    lines = text.splitlines()
    header_lines: list[str] = []
    cells: list[ParsedCell] = []
    current_label: str | None = None
    current_body: list[str] = []
    in_cell = False
    order = 0

    def finish_cell() -> str | None:
        nonlocal order
        body = "\n".join(current_body).strip()
        if not body:
            return "empty cell body"
        info = _define_info(body)
        if info is None:
            return f"cell does not start with a define: {body.splitlines()[0][:60]!r}"
        name, is_function = info
        if current_label is not None and current_label != name:
            # Marker label overrides the define name for identity ONLY if
            # they match; a mismatched label is an authoring error (the
            # cell would be addressable by two different names).
            return f"marker label {current_label!r} does not match define {name!r}"
        cells.append(
            ParsedCell(name=name, label=current_label, text=body, order=order, is_function=is_function)
        )
        order += 1
        return None

    for line in lines:
        m = MARKER_RE.match(line)
        if m:
            if in_cell:
                err = finish_cell()
                if err:
                    return ParsedLibrary(header="\n".join(header_lines), error=err)
            current_label = (m.group("name") or None) if m else None
            current_body = []
            in_cell = True
            continue
        if in_cell:
            current_body.append(line)
        else:
            header_lines.append(line)
    if in_cell:
        err = finish_cell()
        if err:
            return ParsedLibrary(header="\n".join(header_lines), error=err)

    seen: set[str] = set()
    for cell in cells:
        if cell.name in seen:
            return ParsedLibrary(header="\n".join(header_lines), error=f"duplicate cell name {cell.name!r}")
        seen.add(cell.name)

    return ParsedLibrary(header="\n".join(header_lines), cells=cells)


_DEFINE_RE = re.compile(r"^\s*define\s+(function\s+)?([A-Za-z0-9_]+)\s*[(:]", re.IGNORECASE)


def _define_info(body: str) -> tuple[str, bool] | None:
    """Return (define_name, is_function) for a cell body, else None."""
    m = _DEFINE_RE.match(body)
    if not m:
        return None
    return m.group(2), bool(m.group(1))


def refs_of(text: str) -> dict[str, list[str]]:
    """Map define name -> referenced identifiers for one library text.

    Uses the engine parser AST (operations ParseResult carries no AST on
    success). Function parameters are excluded from their own function's
    refs. Includes (other libraries) are NOT refs.
    """
    library = parse_cql(text)
    context_name = getattr(getattr(library, "context", None), "name", None)
    out: dict[str, list[str]] = {}
    for stmt in library.statements:
        name = getattr(stmt, "name", None)
        expr = getattr(stmt, "expression", None)
        if name is None or expr is None:
            continue
        params = _param_names(stmt)
        found: list[str] = []
        _walk_refs(expr, found)
        seen: set[str] = set()
        refs = []
        for ref in found:
            if ref == name or ref in params or ref in seen or ref == context_name:
                continue
            seen.add(ref)
            refs.append(ref)
        out[name] = refs
    return out


def _param_names(stmt: Any) -> set[str]:
    operand = getattr(stmt, "operand", None)
    if operand is None:
        return set()
    # operand: list of ParameterDef-like objects w/ .name
    names = set()
    items = operand if isinstance(operand, (list, tuple)) else [operand]
    for item in items:
        name = getattr(item, "name", None)
        if isinstance(name, str):
            names.add(name)
    return names


def _walk_refs(node: Any, out: list[str]) -> None:
    """Recursive AST walk collecting Identifier names.

    Covers every composite shape the dev-server cells can author:
    binary (left/right), unary/n-ary (operand/operands), function calls
    (arguments), lists (ListExpression.elements), tuples
    (TupleExpression.elements w/ values under .type), and query bodies
    (source/where/return/let/sort clauses). Identifier names inside
    collection-literal function arguments are deps (v2 verification
    blocker: Count({IsMale}) must see IsMale).
    """
    if node is None:
        return
    name = getattr(node, "name", None)
    node_type = type(node).__name__
    if isinstance(name, str) and node_type in ("Identifier", "FunctionRef"):
        out.append(name)
    for attr in (
        "operand", "operands", "arguments", "left", "right", "expression",
        "source", "element", "elements", "type", "where", "return_clause",
        "sort", "let_clauses", "with_clauses", "relationships", "aggregate",
    ):
        child = getattr(node, attr, None)
        if child is None:
            continue
        if isinstance(child, (list, tuple)):
            for item in child:
                _walk_refs(item, out)
        else:
            _walk_refs(child, out)


def dependency_closure(target: str, refs: dict[str, list[str]], available: set[str]) -> list[str]:
    """Transitive closure of cell deps limited to available cells.

    Returns names in file-order-independent topological form — the
    translator resolves order, so ANY deterministic order is fine; we use
    post-order DFS for readability of composed SQL.
    """
    result: list[str] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str) -> None:
        if name in done or name in visiting:
            return
        visiting.add(name)
        for ref in refs.get(name, []):
            if ref in available and ref != name:
                visit(ref)
        visiting.discard(name)
        done.add(name)
        result.append(name)

    visit(target)
    return result


@dataclass
class CellRecord:
    """Server-side per-cell state in a CellSession."""

    status: str = IDLE
    result: dict[str, Any] | None = None  # evaluate envelope slice
    error: str | None = None
    run_seq: int = 0


class CellSession:
    """Working define-set for one library on one WS connection.

    In-memory only: clean on server restart (kernel-clean-per-launch
    doctrine extends to cell state). Kernel restart marks results stale.
    """

    def __init__(self, library_name: str) -> None:
        self.library_name = library_name
        self.lock = threading.Lock()
        self.header_text = ""
        self.cells: dict[str, str] = {}  # name -> cell text (last synced)
        self.order: list[str] = []  # file order of last sync
        self.results: dict[str, CellRecord] = {}
        self.run_counter = 0
        self._dep_texts: dict[str, str] = {}  # cell texts at last sync

    # -- sync --------------------------------------------------------------

    def sync(self, text: str) -> dict[str, Any]:
        """Refresh cell state from the current buffer text.

        Returns a state summary: deleted cells (present before, absent
        now — kept until dependents rerun and fail, per spec), stale
        marks for cells whose deps changed/disappeared, and the split
        error if any.
        """
        parsed = split_cells(text)
        with self.lock:
            self.header_text = parsed.header
            new_cells = {c.name: c.text for c in parsed.cells}
            self.order = [c.name for c in parsed.cells]

            deleted = [n for n in self.cells if n not in new_cells]
            # Deleted-cell retention: keep the record (stale) until a
            # dependent reruns and fails against the missing define; the
            # failing rerun drops it (exact condition pinned by test).
            for name in deleted:
                rec = self.results.get(name)
                if rec is not None:
                    rec.status = STALE

            self.cells = new_cells
            for name in self.cells:
                self.results.setdefault(name, CellRecord())

            # Mark ok/error cells stale when any of their deps changed
            # text or disappeared.
            refs = self._refs_unlocked()
            for name, rec in self.results.items():
                if name not in self.cells:
                    continue
                if rec.status not in (OK, ERROR):
                    continue
                for ref in refs.get(name, []):
                    if ref not in self.cells or new_cells.get(ref) != self._dep_texts.get(ref):
                        rec.status = STALE
                        break
            self._dep_texts = dict(new_cells)

            return {
                "library": self.library_name,
                "error": parsed.error,
                "cells": [
                    {"name": c.name, "is_function": c.is_function, "order": c.order}
                    for c in parsed.cells
                ],
                "deleted": deleted,
                "states": {n: r.status for n, r in self.results.items()},
            }

    def _refs_unlocked(self) -> dict[str, list[str]]:
        try:
            composed = self.header_text + "\n" + "\n".join(self.cells.values())
            return refs_of(composed)
        except Exception:
            return {}

    # -- run planning -------------------------------------------------------

    def plan(self, cell: str, mode: str) -> list[str]:
        """Names to evaluate for a run request (in composition order)."""
        with self.lock:
            if cell not in self.cells:
                raise KeyError(cell)
            if mode == "cell":
                return [cell]
            refs = self._refs_unlocked()
            if mode == "cell_deps":
                return dependency_closure(cell, refs, set(self.cells))
            if mode == "all":
                return list(self.order)
            if mode == "to_here":
                idx = self.order.index(cell)
                return self.order[: idx + 1]
            raise ValueError(f"unknown run mode {mode!r}")

    def compose(self, names: list[str]) -> str:
        """Header + selected cell texts as one synthetic library."""
        with self.lock:
            parts = [self.header_text] if self.header_text.strip() else []
            for name in self.order:  # file order for stable SQL
                if name in names and name in self.cells:
                    parts.append(self.cells[name])
            return "\n\n".join(parts)

    # -- results -------------------------------------------------------------

    def next_run_seq(self) -> int:
        with self.lock:
            self.run_counter += 1
            return self.run_counter

    def set_result(self, name: str, record: CellRecord) -> None:
        with self.lock:
            self.results[name] = record

    def get_result(self, name: str) -> CellRecord | None:
        with self.lock:
            return self.results.get(name)

    def mark_stale_all(self) -> None:
        """Kernel restart: every computed result is stale."""
        with self.lock:
            for rec in self.results.values():
                if rec.status in (OK, ERROR):
                    rec.status = STALE

    def state_summary(self) -> dict[str, Any]:
        with self.lock:
            return {
                "library": self.library_name,
                "cells": [
                    {"name": n, "order": i}
                    for i, n in enumerate(self.order)
                ],
                "states": {n: r.status for n, r in self.results.items()},
            }


class CellSessionRegistry:
    """Per-WS-connection cell sessions (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[int, dict[str, CellSession]] = {}

    def get(self, conn_id: int, library: str) -> CellSession:
        with self._lock:
            per_conn = self._sessions.setdefault(conn_id, {})
            if library not in per_conn:
                per_conn[library] = CellSession(library)
            return per_conn[library]

    def drop(self, conn_id: int) -> None:
        with self._lock:
            self._sessions.pop(conn_id, None)

    def mark_stale_all(self) -> None:
        with self._lock:
            for per_conn in self._sessions.values():
                for session in per_conn.values():
                    session.mark_stale_all()


# ---------------------------------------------------------------------------
# Cell boxes projection (ux3, Muse round-2 Part A)
# ---------------------------------------------------------------------------

# Block keywords a box may contain (besides define). Detected from the
# first meaningful statement in the box body.
_BLOCK_KIND_RE = re.compile(
    r"^\s*(valueset|codesystem|code|concept|parameter|include|context|using|library)\b",
    re.IGNORECASE,
)


@dataclass
class ParsedBox:
    """One marked region of the file, for the boxes projection UI.

    A box is a *view* over a contiguous span of the single library text;
    ``split_boxes`` reports titles + spans; the run protocol continues to
    use ``split_cells`` (define-keyed) unchanged.
    """

    title: str  # explicit label, first define name, or "header"
    title_source: str  # "label" | "define" | "header"
    kind: str  # "define" | "valueset" | "codesystem" | "parameter" | "include" | "header" | "block"
    name: str | None  # define name when the box holds a define (run addressable)
    start: int  # span start offset in the original text (chars)
    end: int  # span end offset (exclusive; marker line INCLUDED for boxes)
    text: str  # the span slice (marker line included for non-header boxes)


def split_boxes(text: str) -> list[ParsedBox]:
    """Split ``text`` into header + marked boxes with char spans.

    Title rule (conductor-locked): explicit ``[name: X]`` wins; otherwise
    the first define name in the box; a box with neither is titled by its
    leading block keyword; the leading un-marked region is the header box.
    Spans tile the file: header [0, first_marker) then each marker line
    through the line before the next marker (or EOF).
    """
    lines = text.splitlines(keepends=True)
    boxes: list[ParsedBox] = []
    offset = 0
    header_end = len(text)
    marker_lines: list[tuple[int, int, str | None]] = []  # (start, end, label)
    for line in lines:
        m = MARKER_RE.match(line.rstrip("\r\n"))
        start = offset
        end = offset + len(line)
        if m:
            if header_end == len(text):
                header_end = start
            marker_lines.append((start, end, (m.group("name") or None)))
        offset = end
    # Header box
    if header_end > 0:
        header_text = text[:header_end]
        boxes.append(
            ParsedBox(
                title="header",
                title_source="header",
                kind="header",
                name=None,
                start=0,
                end=header_end,
                text=header_text,
            )
        )
    elif marker_lines and marker_lines[0][0] == 0:
        pass  # file starts with a marker: no header box
    for i, (m_start, m_end, label) in enumerate(marker_lines):
        b_end = marker_lines[i + 1][0] if i + 1 < len(marker_lines) else len(text)
        body = text[m_end:b_end]
        stripped = body.strip()
        kind = "block"
        name: str | None = None
        d = _DEFINE_RE.match(stripped)
        if d:
            kind = "define"
            name = d.group(2)
        else:
            kb = _BLOCK_KIND_RE.match(stripped)
            if kb:
                kind = kb.group(1).lower()
        if label is not None:
            title, source = label, "label"
        elif name is not None:
            title, source = name, "define"
        elif stripped:
            title, source = kind, "block"
        else:
            title, source = "empty", "block"
        boxes.append(
            ParsedBox(
                title=title,
                title_source=source,
                kind=kind,
                name=name,
                start=m_start,
                end=b_end,
                text=text[m_start:b_end],
            )
        )
    return boxes


def rename_box(
    text: str, box: ParsedBox, new_title: str, all_texts_refs: dict[str, list[str]] | None = None
) -> str:
    """Return the library text after renaming a box title.

    title_source == "label": rewrite the marker label (marker line lives
    at box.start..first newline).
    title_source == "define": rename the define AND every reference to it
    in the rest of the file (callers pass refs via ``all_texts_refs``
    mapping OTHER box define-names -> their refs; simpler and safer: the
    caller refetches refs after the rename, so here we do a whole-file
    identifier-boundary replace of the old define name).
    """
    if not new_title or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", new_title):
        raise ValueError(f"invalid title {new_title!r}")
    if box.title_source == "label":
        line_end = text.index("\n", box.start) if "\n" in text[box.start:] else len(text)
        new_marker = f"// # %% [name: {new_title}]"
        return text[: box.start] + new_marker + text[line_end:]
    if box.title_source == "define" and box.name:
        old = box.name
        pattern = re.compile(rf"\b{re.escape(old)}\b")
        # Rename the define declaration itself plus all references.
        return pattern.sub(new_title, text)
    raise ValueError("cannot rename a header/block box without a label or define")
