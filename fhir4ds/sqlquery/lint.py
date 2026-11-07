"""Static dialect lint for hand-authored SQL bodies.

SQLQuery / SQLView ``content[].data`` payloads are author-controlled raw
SQL. The runner executes them verbatim; DuckDB then fails at execution
time with a parser error whose text may not obviously point at the
dialect mismatch (e.g. a T-SQL ``TOP`` clause surfaces as a syntax
error). This module catches the common "written for another engine"
constructs *before* execution and reports them as warnings.

Design constraints:

* ZERO false positives on valid DuckDB SQL is the bar — every pattern
  here matches syntax DuckDB rejects or silently misreads. Constructs
  DuckDB supports (``::`` casts, ``ILIKE``, ``LIMIT n OFFSET m``,
  ``LIST()``, ``||`` concat, ``NOW()``) are deliberately NOT flagged.
* Warnings, never errors: an exotic-but-valid body must still run. The
  dispatcher surfaces these via ``logging``; callers can also call
  :func:`lint_sql_body` directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

__all__ = ["LintWarning", "lint_sql_body"]


@dataclass(frozen=True)
class LintWarning:
    """One static-lint finding in a SQL body.

    Attributes:
        code: Stable machine-readable identifier (``"non-duckdb-top"``
            etc.) so callers can filter.
        message: Human-readable explanation with the fix direction.
        line: 1-based line number where the pattern matched.
        excerpt: The matched text (trimmed for reporting).
    """

    code: str
    message: str
    line: int
    excerpt: str

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"line {self.line}: {self.message} ({self.excerpt!r})"


# Each entry: (code, regex, message). Regexes are compiled with
# IGNORECASE + MULTILINE and are matched against STRIPPED text
# (comments/strings masked by _mask_literals) so a T-SQL example inside
# a string literal never fires.
_PATTERNS = [
    (
        "non-duckdb-top",
        re.compile(r"\bselect\s+top\s+[^\s(]", re.I),
        "T-SQL `SELECT TOP n` — DuckDB uses `LIMIT n` after the select list",
    ),
    (
        "non-duckdb-isnull",
        re.compile(r"\bisnull\s*\(", re.I),
        "T-SQL `ISNULL(a, b)` — DuckDB uses `COALESCE(a, b)`",
    ),
    (
        "non-duckdb-ifnull",
        re.compile(r"\bifnull\s*\(", re.I),
        "MySQL/SQLite `IFNULL(a, b)` — DuckDB uses `COALESCE(a, b)`",
    ),
    (
        "non-duckdb-nvl",
        re.compile(r"\bnvl\s*\(", re.I),
        "Oracle `NVL(a, b)` — DuckDB uses `COALESCE(a, b)`",
    ),
    (
        "non-duckdb-getdate",
        re.compile(r"\bgetdate\s*\(\s*\)", re.I),
        "T-SQL `GETDATE()` — DuckDB uses `CURRENT_TIMESTAMP` (or `now()`)",
    ),
    (
        "non-duckdb-sysdate",
        re.compile(r"\bsysdate\b", re.I),
        "Oracle `SYSDATE` — DuckDB uses `CURRENT_TIMESTAMP`",
    ),
    (
        "non-duckdb-rownum",
        re.compile(r"\brownum\b", re.I),
        "Oracle `ROWNUM` — DuckDB uses `LIMIT n` or `ROW_NUMBER() OVER ()`",
    ),
    (
        "non-duckdb-backtick-identifier",
        re.compile(r"`[^`]+`"),
        "MySQL backtick identifier — DuckDB quotes identifiers with double quotes",
    ),
    (
        "non-duckdb-bracket-identifier",
        re.compile(r"\b[a-z_][a-z0-9_]*\s*\[[^\]]+\]"),
        "T-SQL `[bracket]` identifier — DuckDB quotes identifiers with double quotes",
    ),
    (
        "non-duckdb-n-string",
        re.compile(r"\bN'"),
        "T-SQL `N'...'` national string prefix — DuckDB strings are plain `'...'`",
    ),
    (
        "non-duckdb-limit-comma",
        re.compile(r"\blimit\s+\d+\s*,\s*\d+", re.I),
        "MySQL `LIMIT offset, count` — DuckDB uses `LIMIT count OFFSET offset`",
    ),
    (
        "non-duckdb-distinct-on",
        re.compile(r"\bselect\s+distinct\s+on\s*\(", re.I),
        "PostgreSQL `SELECT DISTINCT ON (...)` — not supported by DuckDB; "
        "use `ROW_NUMBER() OVER (PARTITION BY ...)` filtering",
    ),
    (
        "non-duckdb-dateadd",
        re.compile(r"\bdateadd\s*\(", re.I),
        "T-SQL `DATEADD(unit, n, d)` — DuckDB uses `d + INTERVAL (n) unit` "
        "or `date_add(d, INTERVAL n unit)`",
    ),
]

_STRING_RE = re.compile(r"'(?:[^']|'')*'")
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _mask_literals(sql: str) -> str:
    """Blank string/comment interiors while preserving delimiters.

    Keeps line numbers, quote characters, and all non-literal text
    intact so pattern matching sees only executable syntax — but
    prefix constructs like ``N'...'`` remain recognizable.
    """
    def _blank_keep_edges(m: "re.Match[str]") -> str:
        text = m.group()
        return text[0] + " " * (len(text) - 2) + text[-1] if len(text) >= 2 else text

    masked = _BLOCK_COMMENT_RE.sub(
        lambda m: re.sub(r"[^\n]", " ", m.group()), sql)
    masked = _LINE_COMMENT_RE.sub(lambda m: " " * len(m.group()), masked)
    masked = _STRING_RE.sub(_blank_keep_edges, masked)
    return masked


def lint_sql_body(sql: str) -> List[LintWarning]:
    """Statically check a SQL body for common non-DuckDB dialect syntax.

    Returns a list of :class:`LintWarning` (empty when the body looks
    like valid DuckDB SQL from a dialect standpoint). Purely advisory:
    this never raises and never blocks execution.
    """
    if not isinstance(sql, str) or not sql.strip():
        return []
    masked = _mask_literals(sql)
    warnings: List[LintWarning] = []
    seen = set()  # (code, line) — one report per pattern per line
    for code, pattern, message in _PATTERNS:
        for m in pattern.finditer(masked):
            line = masked.count("\n", 0, m.start()) + 1
            key = (code, line)
            if key in seen:
                continue
            seen.add(key)
            excerpt = m.group().strip()
            warnings.append(
                LintWarning(code=code, message=message, line=line, excerpt=excerpt)
            )
    return warnings
