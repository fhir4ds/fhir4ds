"""Packaging guards: no untracked Python modules may ship in the package.

Regression origin (2026-11-11, independent review REV-001): during the CMS 2025
campaign, ``fhir4ds/cql/translator/correlate_counts.py`` was created locally and
never staged, while ``retrieve_optimizer.py`` imported it unconditionally::

    from .correlate_counts import correlate_count_subqueries

Every test passed on the developer machine because the file was on disk, but a
clean checkout raised ``ModuleNotFoundError`` for every translation. It stayed
hidden because the local ``.git/config`` had ``status.showUntrackedFiles = no``,
so ``git status`` looked clean.

These tests fail on the *class* of defect rather than the one instance: a module
that exists on disk but is not in git is not part of the branch, so shipping it
in a working tree proves nothing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "fhir4ds"

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(),
    reason="not a git checkout (installed wheel or sdist)",
)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _tracked_python_files() -> set[Path]:
    result = _git("ls-files", "-z", "--", "fhir4ds")
    if result.returncode != 0:
        pytest.skip(f"git ls-files unavailable: {result.stderr.strip()}")
    return {
        (REPO_ROOT / entry).resolve()
        for entry in result.stdout.split("\0")
        if entry.endswith(".py")
    }


def _python_files_on_disk() -> set[Path]:
    """Python files we own — nested repositories (submodules) are excluded.

    ``fhir4ds/cql/tests/official/cql-tests`` is a git submodule with its own
    ``.git``; its files are not ours to stage and are tracked by that repo.
    """
    files = set()
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if _inside_nested_repo(path):
            continue
        files.add(path.resolve())
    return files


def _inside_nested_repo(path: Path) -> bool:
    for parent in path.parents:
        if parent == PACKAGE_ROOT.parent:
            break
        if (parent / ".git").exists():
            return True
    return False


def test_no_untracked_python_modules_in_package():
    """Every .py under fhir4ds/ must be tracked — untracked ones do not ship."""
    untracked = sorted(_python_files_on_disk() - _tracked_python_files())
    assert not untracked, (
        "Untracked Python modules inside the package will be missing from a "
        "clean checkout, breaking imports that pass locally. Stage them:\n  "
        + "\n  ".join(str(p.relative_to(REPO_ROOT)) for p in untracked)
    )


def test_no_tracked_python_module_is_missing_on_disk():
    """The mirror case: a tracked module absent from disk means a broken tree."""
    missing = sorted(_tracked_python_files() - _python_files_on_disk())
    assert not missing, (
        "Modules tracked in git but missing from the working tree:\n  "
        + "\n  ".join(str(p.relative_to(REPO_ROOT)) for p in missing)
    )


def test_git_does_not_hide_untracked_files():
    """``status.showUntrackedFiles=no`` hides exactly the failure above."""
    result = _git("config", "--get", "status.showUntrackedFiles")
    value = (result.stdout or "").strip().lower()
    assert value != "no", (
        ".git/config sets status.showUntrackedFiles=no, which hides untracked "
        "runtime modules (this is how correlate_counts.py escaped). Unset it: "
        "git config --unset status.showUntrackedFiles"
    )


def test_count_correlation_module_is_importable():
    """Direct regression for REV-001: the module the optimizer imports."""
    from fhir4ds.cql.translator.correlate_counts import correlate_count_subqueries

    assert callable(correlate_count_subqueries)


def _pyproject_text() -> str:
    return (REPO_ROOT / "pyproject.toml").read_text()


def test_duckdb2_extra_is_resolvable():
    """QA-D10-001 (v0.0.25): the [duckdb2] extra must never be a dead letter.

    pip INTERSECTS same-package constraints from the base dependencies and
    the requested extras. With an unscoped base pin ``duckdb>=1.5.5,<2``
    and a ``[duckdb2]`` extra requiring ``duckdb>=2.0.0,<2.1``, the
    documented opt-in command ``pip install 'fhir4ds-v2[duckdb2]'`` is a
    ResolutionImpossible error for every user — the exact command the
    0.0.20 release notes recommend. (The extra was originally designed
    against a wide ``>=1.5.5,<3`` base; the 2026-10-30 re-narrowing broke
    it without adjusting the extra.)

    Two states are shippable:
      * the base duckdb pin is scoped ``; extra != 'duckdb2'`` (single-extra
        opt-in resolves duckdb 2.0.x; plain installs keep the 1.5 line), or
      * the base pin allows 2.x outright (the 10-29 atomicity design; then
        the extra narrows to 2.0.x and no marker is needed).
    Anything else — a sub-2 base pin with an unscoped marker while the
    duckdb2 extra demands >=2 — fails here.
    """
    import re

    text = _pyproject_text()
    base = re.search(r'"duckdb>=([\d.]+)(?:,<(\d+))?(?:;([^"]*))?"', text)
    assert base, "base duckdb pin not found in pyproject.toml"
    lower, upper, marker = base.group(1), base.group(2), (base.group(3) or "")
    pin_allows_2x = upper is not None and int(upper) > 2
    extra = re.search(r'duckdb2\s*=\s*\[[^\]]*"duckdb>=([\d.]+)', text)
    assert extra, "[duckdb2] extra not found in pyproject.toml"
    extra_demands_2x = int(extra.group(1).split(".")[0]) >= 2

    if extra_demands_2x and not pin_allows_2x:
        assert "extra != 'duckdb2'" in marker, (
            "The [duckdb2] extra requires duckdb>=2 while the base pin "
            f"stays <{upper} with no extra-scoping marker: pip intersects "
            "the two constraints, so `pip install 'fhir4ds-v2[duckdb2]'` "
            "cannot resolve. Scope the base pin with "
            "`; extra != 'duckdb2'` (see the pyproject comment) or widen "
            "the base past <2 per the 2026-10-29 atomicity ruling."
        )
