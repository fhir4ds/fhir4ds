"""Line-oriented fhir4ds.toml editing for the dev server.

tomllib parses but cannot serialize, and round-tripping through a TOML
writer would drop comments/formatting. ``write_section`` instead edits
the file as text: it replaces (or appends) exactly ONE ``[section]``
block, leaving every other line — comments, whitespace, other tables —
byte-identical. Values are validated before writing so the writer can
never corrupt a workspace config.

Security invariants:
    * Keys are restricted to a per-section allowlist (validated by the
      caller against config.py's parse-side allowlists, re-checked here).
    * String values are single-quote TOML literals when possible and
      basic-quoted with escaping otherwise — never interpolated raw.
    * The API key VALUE never passes through this module (item 1 hard
      rule: the UI/config carry the env var NAME only).
"""

from __future__ import annotations

import re
from pathlib import Path

_SECTION_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _section_re(section: str) -> re.Pattern[str]:
    pat = _SECTION_RE_CACHE.get(section)
    if pat is None:
        pat = re.compile(
            rf"^\[{re.escape(section)}\]\s*(#.*)?$",
        )
        _SECTION_RE_CACHE[section] = pat
    return pat


def _toml_string(value: str) -> str:
    """Render a Python string as a TOML string value (safe)."""
    if value == "":
        return '""'
    if "'" not in value and "\n" not in value and "\r" not in value:
        return f"'{value}'"
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_string(v) for v in value) + "]"
    return _toml_string(str(value))


def write_section(
    toml_path: Path,
    section: str,
    values: dict[str, object],
) -> None:
    """Merge ``values`` into ``[section]`` of ``toml_path`` as text.

    * Existing keys inside the section are replaced (or removed when the
      new value is None); keys not mentioned are preserved.
    * A missing section is appended at end of file (with a leading
      newline separation when the file is non-empty and lacks one).
    * Everything outside the section block is byte-identical.
    * The file is written atomically (tmp + rename).
    """
    section = section.strip()
    if not section or any(ch in section for ch in "[]\n\r"):
        raise ValueError(f"invalid section name: {section!r}")
    for key, value in values.items():
        if not re.fullmatch(r"[A-Za-z0-9_]+", key):
            raise ValueError(f"invalid toml key: {key!r}")

    text = toml_path.read_text(encoding="utf-8") if toml_path.exists() else ""
    lines = text.splitlines(keepends=True)

    start = end = None
    for i, line in enumerate(lines):
        if _section_re(section).match(line.rstrip("\r\n")):
            start = i
            break
    if start is not None:
        # Block extends until the next header line or EOF.
        end = len(lines)
        for j in range(start + 1, len(lines)):
            stripped = lines[j].lstrip()
            if stripped.startswith("["):
                end = j
                break
        block = lines[start + 1 : end]
    else:
        block = None  # append new section

    # Build the merged key -> rendered-line map preserving block order.
    kept: list[str] = []
    if block is not None:
        for line in block:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                kept.append(line)
                continue
            m = re.match(r"([A-Za-z0-9_]+)\s*=", stripped)
            if m and m.group(1) in values:
                continue  # replaced below
            kept.append(line)

    rendered: list[str] = []
    for key, value in values.items():
        if value is None:
            continue  # removed (or simply not written when absent)
        rendered.append(f"{key} = {_render_value(value)}\n")

    if start is not None:
        new_block = [f"[{section}]\n"] + kept + rendered
        if rendered:
            # separate the block from what follows (next header or EOF)
            preceding_blank = bool(kept) and kept[-1].strip() == ""
            following_blank = end < len(lines) and lines[end].strip() == ""
            if not preceding_blank and not following_blank:
                new_block.append("\n")
        lines[start:end] = new_block
    else:
        if lines and not (len(lines) == 1 and lines[0].strip() == ""):
            if not text.endswith("\n"):
                lines[-1] = lines[-1].rstrip("\r\n") + "\n"
            lines.append("\n")
        lines.append(f"[{section}]\n")
        lines.extend(rendered)

    out = "".join(lines)
    tmp = toml_path.with_suffix(toml_path.suffix + ".tmp")
    tmp.write_text(out, encoding="utf-8")
    tmp.replace(toml_path)
