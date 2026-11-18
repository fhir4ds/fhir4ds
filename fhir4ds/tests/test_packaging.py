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


def test_duckdb2_default_on_modern_python():
    """v0.0.25 (Joel ruling 2026-11-18): DuckDB 2.0 is the DEFAULT on
    Python >= 3.11; Python 3.10 keeps the 1.5.x line (2.x wheels are
    cp311+ only). Contract:

      * base pins are python-version scoped:
        - ``duckdb>=1.5.5,<2; python_version < '3.11'``
        - ``duckdb>=2.0.0,<2.1; python_version >= '3.11'``
      * the [duckdb1] extra remains the explicit escape hatch to 1.5.x
      * the [duckdb2] extra stays (explicit 2.0.x pin; on 3.10 it
        resolves to the 1.5.x line by marker design)

    History: QA-D10-001 fixed the extra being a ResolutionImpossible
    dead letter via ``; extra != 'duckdb2'`` scoping; the 2026-11-18
    ruling superseded that with the py-version-scoped default flip
    (v0.0.24 benchmarks: 2.0 ~10x faster at population scale with the
    automatic ``delim_join_as_cte=false`` tuning).
    """
    import re

    text = _pyproject_text()
    pins = dict()
    for lower, upper, marker in re.findall(
        r'"duckdb>=([\d.]+)(?:,<([\d.]+))?(?:;([^"]*))?"', text
    ):
        pins[marker.strip()] = (lower, upper)

    old = pins.get("python_version < '3.11'")
    assert old and old[1] == "2", (
        "Python 3.10 base pin must stay >=1.5.5,<2 (no 2.x wheels exist "
        f"there); got {old}"
    )
    new = pins.get("python_version >= '3.11'")
    assert new and new[0].split(".")[0] == "2", (
        "Python >= 3.11 base pin must default to the DuckDB 2.0.x line "
        f"per the 2026-11-18 ruling; got {new}"
    )
    extra1 = re.search(r"duckdb1\s*=\s*\[[^\]]*duckdb>=([\d.]+)(?:,<(\d+))?", text)
    assert extra1 and extra1.group(2) == "2", (
        "[duckdb1] extra must pin the 1.5.x line as the escape hatch"
    )

