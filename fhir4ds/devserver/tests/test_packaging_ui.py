"""c-wasm-bolton closeout R1: wheel/sdist packaging of the wasm UI build.

The 61MB committed static-wasm build is EXCLUDED from the wheel (the wheel
stays lean; baseline static/ was 420KB). The sdist carries it so
source installs serve the UI out of the box. Dev-server from a git
checkout serves it as-is.
"""

import tarfile
import zipfile
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_wheel_exclude_config_present():
    pyproject = (_repo_root() / "pyproject.toml").read_text()
    assert "[tool.hatch.build.targets.wheel]" in pyproject
    assert 'exclude = ["fhir4ds/devserver/static-wasm"]' in pyproject


def test_static_wasm_build_present_in_tree():
    # The committed build must exist for sdist/git-checkout serving.
    root = _repo_root() / "fhir4ds" / "devserver" / "static-wasm"
    assert (root / "index.html").is_file(), "committed wasm UI build missing"
    assert any((root / "assets").glob("main-*.js")), "entry bundle missing"


@pytest.mark.skipif(
    not (_repo_root() / "dist").is_dir(), reason="no built artifacts in dist/"
)
def test_wheel_omits_static_wasm_and_sdist_includes_it():
    dist = _repo_root() / "dist"
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    assert wheels, "expected at least one wheel in dist/"
    with zipfile.ZipFile(wheels[-1]) as whl:
        names = whl.namelist()
        assert not any("static-wasm" in n for n in names), (
            "wheel ships the 61MB static-wasm build (R1 regression)"
        )
    if sdists:
        with tarfile.open(sdists[-1]) as tar:
            members = tar.getnames()
            assert any("static-wasm/index.html" in m for m in members), (
                "sdist must carry the wasm UI build"
            )
