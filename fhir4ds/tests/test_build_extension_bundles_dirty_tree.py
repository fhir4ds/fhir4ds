"""`scripts/build_extension_bundles.py` must never discard uncommitted source edits.

Found the hard way (WP-5, 2026-11-25): the dirty-tree refusal sat inside
`build_one`'s try block, so the `finally` ran `git checkout HEAD -- <src>` on the
very changes it was refusing and a 69-line C++ fix vanished from the worktree.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_extension_bundles.py"
SLOT_SUFFIX = ".duckdb156_extension"
SLOT_ABI = "1.5.6"


def _load_script():
    spec = importlib.util.spec_from_file_location("build_extension_bundles", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the module's annotations through sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _configure(repo: Path) -> None:
    _git(repo, "config", "user.email", "tests@example.com")
    _git(repo, "config", "user.name", "fhir4ds tests")


@pytest.fixture()
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A throwaway repository with one committed extension and a submodule dir.

    Returns (module, repo, source file, runs). `runs` records every command the
    script executes.
    """
    repo = tmp_path / "repo"
    source = repo / "extensions" / "demo" / "src" / "a.cpp"
    submodule = repo / "extensions" / "demo" / "duckdb"
    source.parent.mkdir(parents=True)
    submodule.mkdir(parents=True)
    _git(repo, "init", "-q")
    _configure(repo)
    source.write_text("int original;\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(submodule, "init", "-q")
    _configure(submodule)
    (submodule / "CMakeLists.txt").write_text("# duckdb stand-in; no version tags\n")
    _git(submodule, "add", "-A")
    _git(submodule, "commit", "-q", "-m", "submodule")

    module = _load_script()
    monkeypatch.setattr(module, "REPO_ROOT", repo)

    runs: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        runs.append([str(part) for part in cmd])
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", spy)
    return module, repo, source, runs


def _slot(module, source_pin: str | None = None):
    return module.Slot(
        extension="demo", abi=SLOT_ABI, suffix=SLOT_SUFFIX, source_pin=source_pin
    )


def test_dirty_source_tree_is_refused_and_left_untouched(fake_repo):
    module, repo, source, runs = fake_repo
    source.write_text("int uncommitted_fix;\n")

    assert module.build_one(_slot(module), dry_run=False) is False

    # The refusal must not "restore" anything: the edit is still there and no
    # build was started.
    assert source.read_text() == "int uncommitted_fix;\n"
    assert _git(repo, "status", "--porcelain", "--", "extensions/demo/src") == "M extensions/demo/src/a.cpp"
    assert not any(cmd[0] == "make" for cmd in runs)
    assert not any(
        cmd[:4] == ["git", "checkout", "-q", "HEAD"] for cmd in runs
    ), runs


def test_clean_tree_dry_run_touches_nothing(fake_repo):
    module, _repo, _source, runs = fake_repo

    assert module.build_one(_slot(module), dry_run=True) is True

    assert all(cmd[0] == "git" for cmd in runs), runs
    assert not any("checkout" in cmd for cmd in runs), runs


def test_pinned_sources_are_restored_after_a_failed_build(fake_repo):
    module, repo, source, _runs = fake_repo
    base = _git(repo, "rev-parse", "HEAD")
    source.write_text("int second;\n")
    _git(repo, "commit", "-q", "-am", "second")

    # The duckdb stand-in has no `v1.5.6` tag, so the build stops right after the
    # sources were pinned; the finally block must put them back.
    assert module.build_one(_slot(module, source_pin=base), dry_run=False) is False

    assert source.read_text() == "int second;\n"
    assert _git(repo, "status", "--porcelain", "--", "extensions/demo/src") == ""
