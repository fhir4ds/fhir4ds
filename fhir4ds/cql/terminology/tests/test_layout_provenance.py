"""D12 (v0.0.20): medterm4ds search provenance — fhir4ds/terminology layout pin.

Joel rule (2026-11-01): any medterm4ds search fhir4ds uses must pull its
data from the HuggingFace ``fhir4ds/terminology`` repo. The in-process
adapter pins ``MEDTERM4DS_LAYOUT=terminology`` (before the first
medterm4ds import) whenever a fhir4ds/terminology release is cached
locally, so serving binds the release artifacts explicitly instead of
silently falling back to a legacy revision cache.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def _make_release(root: Path, repo: str, release: str = "2099.01.01.1") -> None:
    d = root / "terminology" / release
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"repo": repo, "release": release}))


def test_pins_terminology_when_release_cached(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDTERM4DS_LAYOUT", raising=False)
    _make_release(tmp_path, "fhir4ds/terminology")
    from fhir4ds.cql.terminology.in_process_adapter import prefer_terminology_layout

    assert prefer_terminology_layout(tmp_path) == "terminology"
    assert os.environ["MEDTERM4DS_LAYOUT"] == "terminology"


def test_leaves_auto_when_no_release(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDTERM4DS_LAYOUT", raising=False)
    from fhir4ds.cql.terminology.in_process_adapter import prefer_terminology_layout

    assert prefer_terminology_layout(tmp_path) == "auto"


def test_ignores_foreign_repo_manifests(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDTERM4DS_LAYOUT", raising=False)
    _make_release(tmp_path, "someone-else/terminology")
    from fhir4ds.cql.terminology.in_process_adapter import prefer_terminology_layout

    assert prefer_terminology_layout(tmp_path) == "auto"


def test_never_overrides_operator_pin(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDTERM4DS_LAYOUT", "legacy")
    _make_release(tmp_path, "fhir4ds/terminology")
    from fhir4ds.cql.terminology.in_process_adapter import prefer_terminology_layout

    assert prefer_terminology_layout(tmp_path) == "legacy"


def test_no_medterm4ds_import_inside_helper():
    """The pin must be import-free: medterm4ds's package __init__ pulls
    services.search, which reads MEDTERM4DS_LAYOUT at import time."""
    code = (
        "import sys, json, tempfile, pathlib\n"
        "root = pathlib.Path(tempfile.mkdtemp())\n"
        "d = root / 'terminology' / '2099.01.01.1'\n"
        "d.mkdir(parents=True)\n"
        "(d / 'manifest.json').write_text(json.dumps({'repo': 'fhir4ds/terminology'}))\n"
        "from fhir4ds.cql.terminology.in_process_adapter import prefer_terminology_layout\n"
        "assert prefer_terminology_layout(root) == 'terminology'\n"
        "assert not any(m.startswith('medterm4ds') for m in sys.modules), list(sys.modules)[:5]\n"
        "print('IMPORT-FREE OK')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "MEDTERM4DS_LAYOUT"}
    env["PYTHONPATH"] = str(REPO)
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120
    )
    assert out.returncode == 0, out.stderr[-400:]
    assert "IMPORT-FREE OK" in out.stdout
